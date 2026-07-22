from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ApprovalRequired, PermissionDenied
from app.domain.models import AiCommandApproval, AiSession, ApprovalRequest, Server, User
from app.domain.models.enums import ApprovalStatus
from app.domain.models.enums import AuditResult, PolicyDecision
from app.services.audit_service import AuditService
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.services.ssh_gateway import SshGateway
from app.services.tool_registry import ToolRegistry
from app.services.tool_configuration_service import resolve_effective_tool


class OperationService:
    def __init__(
        self,
        session: AsyncSession,
        registry: ToolRegistry,
        ssh_gateway: SshGateway,
    ) -> None:
        self.session = session
        self.registry = registry
        self.ssh_gateway = ssh_gateway
        self.policy = PolicyEngine(session)
        self.audit = AuditService(session)

    async def execute_tool(
        self,
        *,
        user: User,
        server: Server,
        action: str,
        arguments: dict,
        reason: str,
        session_id: str | None,
        approval_id: str | None = None,
    ) -> dict:
        tool = await resolve_effective_tool(self.session, self.registry, action)
        if not self.registry.supports_target(tool, server.server_type, server.os):
            raise PermissionDenied("Tool is not allowed for this server target type")
        command = self.registry.render_command(action, server.os, arguments)
        if action == "run_ssh_command" and approval_id is None:
            await self._require_command_consent(
                user=user, server=server, command=command, arguments=arguments,
                reason=reason, session_id=session_id,
            )
        approved_request = await self._validate_approval(
            approval_id=approval_id,
            user=user,
            server=server,
            action=action,
            arguments=arguments,
        )
        consent_only = bool(approved_request and
                            approved_request.plan.get("kind") == "ai_command_consent")
        decision = (
            PolicyDecision.allow
            if approved_request is not None and not consent_only
            else await self.policy.evaluate(
                PolicyContext(
                    user=user,
                    server=server,
                    action=action,
                    tool=tool,
                    requested_at=datetime.now(UTC),
                )
            )
        )
        if decision == PolicyDecision.deny:
            await self.audit.record(
                user_id=user.id,
                session_id=session_id,
                server_id=server.id,
                prompt=reason,
                reasoning_summary="Policy denied execution before SSH command dispatch.",
                tool_name=action,
                ssh_command=command,
                output=None,
                decision=decision,
                duration_ms=0,
                result=AuditResult.denied,
            )
            await self.session.commit()
            raise PermissionDenied("Policy denied this operation")
        if decision == PolicyDecision.approval_required:
            approval = ApprovalRequest(
                requested_by_user_id=user.id,
                server_id=server.id,
                action=action,
                reason=reason,
                impact=f"{action} on {server.hostname} may affect service availability.",
                plan={
                    "action": action,
                    "arguments": arguments,
                    "command_ref": self._redacted_ref(command),
                },
            )
            self.session.add(approval)
            await self.session.flush()
            await self.audit.record(
                user_id=user.id,
                session_id=session_id,
                server_id=server.id,
                prompt=reason,
                reasoning_summary="Policy requires human approval. Execution was not dispatched.",
                tool_name=action,
                ssh_command=command,
                output=None,
                decision=decision,
                duration_ms=0,
                result=AuditResult.approval_required,
            )
            await self.session.commit()
            raise ApprovalRequired(approval.id)

        if approved_request is not None:
            approved_request.status = ApprovalStatus.executed
            await self.session.flush()
        try:
            result = await self.ssh_gateway.execute(server, command)
        except AppError as exc:
            await self.audit.record(
                user_id=user.id,
                session_id=session_id,
                server_id=server.id,
                prompt=reason,
                reasoning_summary="SSH gateway rejected or failed controlled execution.",
                tool_name=action,
                ssh_command=command,
                output=exc.message,
                decision=decision,
                duration_ms=0,
                result=AuditResult.failed,
            )
            await self.session.commit()
            raise
        await self.audit.record(
            user_id=user.id,
            session_id=session_id,
            server_id=server.id,
            prompt=reason,
            reasoning_summary="Approved read/write tool executed through backend SSH gateway.",
            tool_name=action,
            ssh_command=command,
            output=result.stdout or result.stderr,
            decision=decision,
            duration_ms=result.duration_ms,
            exit_code=result.exit_code,
            approval_used=approved_request is not None,
            result=AuditResult.success if result.exit_code == 0 else AuditResult.failed,
        )
        return {
            "action": action,
            "server_id": server.id,
            "decision": decision,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "command_ref": self._redacted_ref(command),
            "approval_id": None,
            "confidence": {
                "score": 0.84 if result.exit_code == 0 else 0.48,
                "reason": "Direct command output from controlled backend tool.",
                "need_more_data": result.exit_code != 0,
            },
        }

    async def _require_command_consent(
        self, *, user: User, server: Server, command: str, arguments: dict,
        reason: str, session_id: str | None,
    ) -> None:
        command_hash = sha256(command.encode("utf-8")).hexdigest()
        ai_session = await self.session.get(AiSession, session_id) if session_id else None
        if ai_session and ai_session.user_id == user.id and ai_session.accept_all_commands:
            return
        remembered = await self.session.scalar(select(AiCommandApproval.id).where(
            AiCommandApproval.user_id == user.id,
            AiCommandApproval.system_id == server.system_id,
            AiCommandApproval.server_id == server.id,
            AiCommandApproval.command_hash == command_hash,
            AiCommandApproval.is_active.is_(True),
        ))
        if remembered:
            return
        approval = ApprovalRequest(
            requested_by_user_id=user.id, server_id=server.id, action="run_ssh_command",
            reason=reason,
            impact="Read-only command proposed by AI; backend policy still applies after consent.",
            plan={"kind": "ai_command_consent", "session_id": session_id,
                  "system_id": server.system_id, "arguments": arguments,
                  "command": command, "command_hash": command_hash},
        )
        self.session.add(approval)
        await self.session.flush()
        await self.audit.record(
            user_id=user.id, session_id=session_id, server_id=server.id, prompt=reason,
            reasoning_summary="Waiting for user consent before policy evaluation and SSH dispatch.",
            tool_name="run_ssh_command", ssh_command=command, output=None,
            decision="command_consent_required", duration_ms=0,
            result=AuditResult.approval_required,
        )
        await self.session.commit()
        raise ApprovalRequired(approval.id)

    async def _validate_approval(
        self,
        *,
        approval_id: str | None,
        user: User,
        server: Server,
        action: str,
        arguments: dict,
    ) -> ApprovalRequest | None:
        if approval_id is None:
            return None
        approval = await self.session.get(ApprovalRequest, approval_id, with_for_update=True)
        if (
            approval is None
            or approval.status != ApprovalStatus.approved
            or approval.requested_by_user_id != user.id
            or approval.server_id != server.id
            or approval.action != action
            or approval.plan.get("arguments", {}) != arguments
        ):
            raise PermissionDenied("Approval is invalid, consumed, or does not match this request")
        return approval

    def _redacted_ref(self, command: str) -> str:
        digest = sha256(command.encode("utf-8")).hexdigest()[:16]
        return f"backend-mapped:{digest}"
