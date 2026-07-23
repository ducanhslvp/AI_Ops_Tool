import json
from datetime import UTC, datetime
from hashlib import sha256

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Depends

from app.ai.gateway import AIGateway
from app.core.exceptions import AppError, ApprovalRequired
from app.api.dependencies import (
    DbSession, get_gateway, get_ssh_gateway, get_tool_registry, require_permission,
)
from app.domain.models import (
    AiCommandApproval, AiMemory, AiMessage, AiSession, ApprovalRequest, AuditLog, Server,
    System, User,
)
from app.domain.models.enums import ApprovalStatus, AuditResult
from app.schemas.operations import (
    AiChatRequest, AiChatResponse, AiCommandConsentDecision, AiProviderSwitchRequest,
    AiSessionBypassRequest, AiSessionCreate, AiSessionUpdate,
)
from app.schemas.common import PaginationDep, set_pagination_headers
from app.services.ai_service import AiService
from app.services.audit_service import AuditService
from app.services.operation_service import OperationService
from app.services.ssh_gateway import SshGateway
from app.services.tool_registry import ToolRegistry

router = APIRouter(prefix="/ai", tags=["ai"])


async def _completed_command_consent_result(
    session: AsyncSession, consent: ApprovalRequest,
) -> dict:
    """Return a stable result for retries without dispatching the command again."""
    plan = dict(consent.plan or {})
    existing = plan.get("execution_result")
    if isinstance(existing, dict):
        return {**existing, "idempotent": True}

    if consent.status == ApprovalStatus.approved:
        return {
            "action": "run_ssh_command",
            "decision": "processing",
            "approval_id": consent.id,
            "idempotent": True,
        }

    audit = await session.scalar(
        select(AuditLog)
        .where(
            AuditLog.session_id == str(plan.get("session_id") or ""),
            AuditLog.server_id == consent.server_id,
            AuditLog.tool_name == "run_ssh_command",
            AuditLog.ssh_command == str(plan.get("command") or ""),
        )
        .order_by(AuditLog.sequence_number.desc())
        .limit(1)
    )
    if audit is not None:
        succeeded = audit.result == AuditResult.success
        recovered = {
            "action": "run_ssh_command",
            "server_id": consent.server_id,
            "decision": "allow" if succeeded else "rejected",
            "stdout": audit.output or "" if succeeded else "",
            "stderr": "" if succeeded else audit.output or "",
            "exit_code": audit.exit_code,
            "approval_id": consent.id,
            "error": None if succeeded else audit.output or "SSH command execution failed",
            "recovered_from_audit": True,
        }
    else:
        recovered = {
            "action": "run_ssh_command",
            "server_id": consent.server_id,
            "decision": "rejected",
            "approval_id": consent.id,
            "error": "The prior command decision completed without a stored execution result",
            "recovered_from_audit": False,
        }
    consent.plan = {**plan, "execution_result": recovered}
    await session.commit()
    return {**recovered, "idempotent": True}


@router.post("/command-consents/{consent_id}/decision")
async def decide_command_consent(
    consent_id: str,
    payload: AiCommandConsentDecision,
    session: DbSession,
    registry: ToolRegistry = Depends(get_tool_registry),
    ssh_gateway: SshGateway = Depends(get_ssh_gateway),
    user: User = Depends(require_permission("ai:chat")),
) -> dict:
    consent = await session.get(ApprovalRequest, consent_id, with_for_update=True)
    if (consent is None or consent.requested_by_user_id != user.id
            or consent.plan.get("kind") != "ai_command_consent"):
        raise HTTPException(status_code=404, detail="Command consent not found")
    if consent.status != ApprovalStatus.pending:
        return await _completed_command_consent_result(session, consent)
    consent.decided_by_user_id = user.id
    consent.decided_at = datetime.now(UTC)
    if payload.decision == "reject":
        consent.status = ApprovalStatus.rejected
        rejected = {"decision": "rejected", "approval_id": consent.id,
                    "error": "User rejected the proposed SSH command"}
        consent.plan = {
            **consent.plan, "consent_decision": payload.decision,
            "execution_result": rejected,
        }
        await session.commit()
        return rejected

    plan = consent.plan
    ai_session = await session.get(AiSession, plan.get("session_id"))
    server = await session.get(Server, consent.server_id)
    if ai_session is None or ai_session.user_id != user.id or server is None:
        raise HTTPException(status_code=409, detail="Command consent scope is no longer valid")
    if payload.decision == "accept_session":
        ai_session.accept_all_commands = True
    if payload.decision == "accept_command":
        command = str(plan.get("command") or "")
        command_hash = str(plan.get("command_hash") or sha256(command.encode()).hexdigest())
        existing = await session.scalar(select(AiCommandApproval).where(
            AiCommandApproval.user_id == user.id,
            AiCommandApproval.system_id == server.system_id,
            AiCommandApproval.server_id == server.id,
            AiCommandApproval.command_hash == command_hash,
        ))
        if existing:
            existing.is_active = True
            existing.command = command
            existing.effect = "allow"
            existing.last_used_at = datetime.now(UTC)
        else:
            session.add(AiCommandApproval(
                user_id=user.id, system_id=server.system_id, server_id=server.id,
                command_hash=command_hash, command=command, effect="allow",
                description="Allowed from AI command consent", is_active=True,
                use_count=1, last_used_at=datetime.now(UTC),
            ))
    consent.status = ApprovalStatus.approved
    await session.flush()
    try:
        execution = await OperationService(session, registry, ssh_gateway).execute_tool(
            user=user, server=server, action="run_ssh_command",
            arguments=dict(plan.get("arguments") or {}),
            reason="User approved an AI-proposed read-only SSH command",
            session_id=ai_session.id, approval_id=consent.id,
        )
    except ApprovalRequired as exc:
        execution = {"action": "run_ssh_command", "decision": "approval_required",
                     "approval_id": exc.approval_id,
                     "error": "Organization policy requires independent approval"}
    except AppError as exc:
        execution = {
            "action": "run_ssh_command", "server_id": server.id,
            "decision": "rejected", "approval_id": consent.id,
            "error": exc.message,
        }
    consent.plan = {
        **consent.plan, "consent_decision": payload.decision,
        "execution_result": execution,
    }
    await session.commit()
    return {**execution, "consent_scope": payload.decision}


@router.post("/chat", response_model=AiChatResponse)
async def chat(
    payload: AiChatRequest,
    session: DbSession,
    gateway: AIGateway = Depends(get_gateway),
    registry: ToolRegistry = Depends(get_tool_registry),
    ssh_gateway: SshGateway = Depends(get_ssh_gateway),
    user: User = Depends(require_permission("ai:chat")),
) -> AiChatResponse:
    result = await AiService(session, gateway, registry, ssh_gateway).chat(
        user=user,
        message=payload.message,
        session_id=payload.session_id,
        system_id=payload.system_id,
        server_id=payload.server_id,
        model=payload.model, reasoning_effort=payload.reasoning_effort,
        include_full_memory=payload.include_full_memory,
        internal_continuation=payload.internal_continuation,
    )
    await session.commit()
    return AiChatResponse(**result)


@router.post("/chat/stream")
async def stream_chat(
    payload: AiChatRequest,
    session: DbSession,
    gateway: AIGateway = Depends(get_gateway),
    registry: ToolRegistry = Depends(get_tool_registry),
    ssh_gateway: SshGateway = Depends(get_ssh_gateway),
    user: User = Depends(require_permission("ai:chat")),
) -> StreamingResponse:
    service = AiService(session, gateway, registry, ssh_gateway)

    async def events():
        try:
            async for event in service.stream_chat(
                user=user, message=payload.message, session_id=payload.session_id,
                system_id=payload.system_id, server_id=payload.server_id,
                model=payload.model, reasoning_effort=payload.reasoning_effort,
                include_full_memory=payload.include_full_memory,
                internal_continuation=payload.internal_continuation,
            ):
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/providers")
async def providers(
    gateway: AIGateway = Depends(get_gateway),
    _: User = Depends(require_permission("ai:chat")),
) -> dict:
    configured = gateway.manager.config.providers.get(gateway.manager.active_name) if gateway.manager.config else None
    try:
        catalog = await gateway.manager.model_catalog()
    except Exception:
        configured_models = list(configured.extra.get("models", [])) if configured else []
        default_model = configured.model if configured else ""
        fallback = list(dict.fromkeys(item for item in [default_model, *configured_models] if item))
        catalog = [{"id": item, "display_name": item, "description": "",
                    "is_default": item == default_model, "default_reasoning_effort": "medium",
                    "reasoning_efforts": ["low", "medium", "high"]} for item in fallback]
    models = [item["id"] for item in catalog]
    efforts = list(dict.fromkeys(
        effort for item in catalog for effort in item.get("reasoning_efforts", [])
    )) or ["low", "medium", "high"]
    return {"active_provider": gateway.manager.active_name,
            "exclusive_mode": gateway.manager.exclusive, "providers": gateway.providers(),
            "models": models, "model_catalog": catalog, "reasoning_efforts": efforts}


@router.get("/providers/health")
async def provider_health(
    gateway: AIGateway = Depends(get_gateway),
    _: User = Depends(require_permission("ai:chat")),
) -> dict:
    return {"providers": [item.model_dump() for item in await gateway.health()]}


@router.post("/providers/switch")
async def switch_provider(
    payload: AiProviderSwitchRequest,
    gateway: AIGateway = Depends(get_gateway),
    _: User = Depends(require_permission("*")),
) -> dict:
    await gateway.switch_provider(payload.provider)
    return {"active_provider": gateway.manager.active_name}


@router.post("/providers/reload")
async def reload_providers(
    gateway: AIGateway = Depends(get_gateway),
    _: User = Depends(require_permission("*")),
) -> dict:
    await gateway.reload()
    return {"active_provider": gateway.manager.active_name}


@router.post("/providers/{provider}/reconnect")
async def reconnect_provider(
    provider: str,
    gateway: AIGateway = Depends(get_gateway),
    _: User = Depends(require_permission("*")),
) -> dict:
    health = await gateway.manager.reconnect(provider)
    return health.model_dump()


@router.post("/requests/{request_id}/cancel")
async def cancel_request(
    request_id: str,
    gateway: AIGateway = Depends(get_gateway),
    _: User = Depends(require_permission("ai:chat")),
) -> dict:
    return {"request_id": request_id, "cancelled": await gateway.cancel(request_id)}


@router.get("/sessions")
async def list_ai_sessions(
    session: DbSession,
    response: Response,
    pagination: PaginationDep,
    system_id: str,
    user: User = Depends(require_permission("ai:chat")),
) -> list[dict]:
    total = await session.scalar(select(func.count(AiSession.id)).where(
        AiSession.user_id == user.id, AiSession.system_id == system_id)) or 0
    set_pagination_headers(response, total, pagination)
    items = (await session.scalars(select(AiSession).where(
        AiSession.user_id == user.id, AiSession.system_id == system_id)
        .order_by(AiSession.last_activity_at.desc(), AiSession.updated_at.desc()).offset(pagination.offset).limit(
            pagination.page_size))).all()
    return [{"id": item.id, "system_id": item.system_id, "title": item.title,
             "status": item.status, "last_activity_at": item.last_activity_at,
             "context_size": item.context_size, "memory": item.memory, "model": item.model,
             "reasoning_effort": item.reasoning_effort,
             "include_full_memory": item.include_full_memory,
             "bypass_policy": item.bypass_policy,
             "created_at": item.created_at, "updated_at": item.updated_at} for item in items]


@router.post("/sessions", status_code=201)
async def create_ai_session(
    payload: AiSessionCreate,
    session: DbSession,
    user: User = Depends(require_permission("ai:chat")),
) -> dict:
    if await session.get(System, payload.system_id) is None:
        raise HTTPException(status_code=404, detail="System not found")
    item = AiSession(user_id=user.id, system_id=payload.system_id, title=payload.title.strip(),
                     memory={"checked_tools": []}, status="idle", model=payload.model,
                     reasoning_effort=payload.reasoning_effort,
                     include_full_memory=payload.include_full_memory)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return {"id": item.id, "system_id": item.system_id, "title": item.title,
            "status": item.status, "model": item.model,
            "reasoning_effort": item.reasoning_effort,
            "include_full_memory": item.include_full_memory,
            "bypass_policy": item.bypass_policy,
            "created_at": item.created_at, "updated_at": item.updated_at}


@router.get("/sessions/{session_id}")
async def get_ai_session(
    session_id: str,
    session: DbSession,
    user: User = Depends(require_permission("ai:chat")),
) -> dict:
    item = await session.get(AiSession, session_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="AI session not found")
    message_total = await session.scalar(select(func.count(AiMessage.id)).where(
        AiMessage.session_id == item.id)) or 0
    messages = list((await session.scalars(select(AiMessage).where(
        AiMessage.session_id == item.id).order_by(
            AiMessage.created_at.desc(), AiMessage.id.desc()).limit(50))).all())
    messages.reverse()
    return {"id": item.id, "system_id": item.system_id, "title": item.title,
            "status": item.status, "last_activity_at": item.last_activity_at,
            "context_size": item.context_size, "memory": item.memory, "model": item.model,
            "reasoning_effort": item.reasoning_effort,
            "include_full_memory": item.include_full_memory,
            "bypass_policy": item.bypass_policy,
            "messages_has_more": message_total > len(messages),
            "messages": [{"id": message.id, "role": message.role, "content": message.content,
                          "tool_events": message.tool_events, "confidence": message.confidence,
                          "created_at": message.created_at} for message in messages]}


@router.get("/sessions/{session_id}/messages")
async def get_ai_session_messages(
    session_id: str,
    session: DbSession,
    before: datetime | None = None,
    before_id: str | None = None,
    limit: int = Query(default=50, ge=10, le=100),
    user: User = Depends(require_permission("ai:chat")),
) -> dict:
    item = await session.get(AiSession, session_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="AI session not found")
    statement = select(AiMessage).where(AiMessage.session_id == item.id)
    if before is not None:
        statement = statement.where(
            or_(
                AiMessage.created_at < before,
                and_(AiMessage.created_at == before, AiMessage.id < before_id),
            ) if before_id else AiMessage.created_at < before
        )
    messages = list((await session.scalars(statement.order_by(
        AiMessage.created_at.desc(), AiMessage.id.desc()).limit(limit + 1))).all())
    has_more = len(messages) > limit
    messages = messages[:limit]
    messages.reverse()
    return {
        "items": [{"id": message.id, "role": message.role, "content": message.content,
                   "tool_events": message.tool_events, "confidence": message.confidence,
                   "created_at": message.created_at} for message in messages],
        "has_more": has_more,
        "next_before": messages[0].created_at if has_more and messages else None,
    }


@router.patch("/sessions/{session_id}")
async def update_ai_session(
    session_id: str,
    payload: AiSessionUpdate,
    session: DbSession,
    user: User = Depends(require_permission("ai:chat")),
) -> dict:
    item = await session.get(AiSession, session_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="AI session not found")
    values = payload.model_dump(exclude_unset=True)
    if "title" in values:
        item.title = values["title"].strip()
    # Bypass has a dedicated administrator-only endpoint and cannot be smuggled through
    # ordinary conversation preferences.
    values.pop("bypass_policy", None)
    for field in ("model", "reasoning_effort", "include_full_memory"):
        if field in values:
            setattr(item, field, values[field])
    await session.commit()
    return {"id": item.id, "system_id": item.system_id, "title": item.title,
            "status": item.status, "model": item.model,
            "reasoning_effort": item.reasoning_effort,
            "include_full_memory": item.include_full_memory,
            "bypass_policy": item.bypass_policy,
            "updated_at": item.updated_at}


@router.put("/sessions/{session_id}/policy-bypass")
async def set_ai_session_policy_bypass(
    session_id: str,
    payload: AiSessionBypassRequest,
    session: DbSession,
    actor: User = Depends(require_permission("ai:policy_bypass")),
) -> dict:
    item = await session.get(AiSession, session_id)
    if item is None or item.user_id != actor.id:
        raise HTTPException(status_code=404, detail="AI session not found")
    item.bypass_policy = payload.enabled
    await AuditService(session).record(
        user_id=actor.id,
        session_id=item.id,
        server_id=None,
        prompt="Authorized operator changed session-only AI policy bypass.",
        reasoning_summary=(
            "Policy and approval bypass enabled for this AI session; command validation, "
            "SSH Gateway controls and audit remain active."
            if payload.enabled
            else "Session-only AI policy bypass disabled."
        ),
        tool_name="session_policy_bypass",
        ssh_command=None,
        output=f"enabled={payload.enabled}",
        decision="bypass_enabled" if payload.enabled else "bypass_disabled",
        duration_ms=0,
        result=AuditResult.success,
    )
    await session.commit()
    return {"session_id": item.id, "bypass_policy": item.bypass_policy}


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_ai_session(
    session_id: str,
    session: DbSession,
    user: User = Depends(require_permission("ai:chat")),
) -> Response:
    item = await session.get(AiSession, session_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="AI session not found")
    messages = (await session.scalars(select(AiMessage).where(
        AiMessage.session_id == item.id))).all()
    for message in messages:
        await session.delete(message)
    await session.execute(update(AiMemory).where(AiMemory.session_id == item.id).values(
        session_id=None))
    await session.delete(item)
    await session.commit()
    return Response(status_code=204)
