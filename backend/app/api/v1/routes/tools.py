import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from app.api.dependencies import (
    DbSession,
    get_server_or_404,
    get_ssh_gateway,
    get_tool_registry,
    require_permission,
)
from app.domain.models import ApprovalRequest, Server, System, ToolConfiguration, User
from app.core.exceptions import AppError
from app.domain.models.enums import AuditResult, PolicyDecision
from app.schemas.operations import (
    ToolDescriptor,
    ToolDescriptorUpdate,
    ToolExecutionRequest,
    ToolExecutionResponse,
    MultiServerExecutionRequest,
    MultiServerExecutionResult,
)
from app.services.operation_service import OperationService
from app.services.audit_service import AuditService
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.services.ssh_gateway import SshGateway
from app.services.tool_registry import ToolRegistry
from app.services.tool_configuration_service import list_effective_tools, resolve_effective_tool
from app.workspace import WorkspaceBuilder

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[ToolDescriptor])
async def list_tools(
    session: DbSession,
    _: User = Depends(require_permission("policy:read")),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> list[ToolDescriptor]:
    return [
        ToolDescriptor(
            name=tool.name,
            plugin=tool.plugin,
            description=tool.description,
            risk_level=tool.risk_level,
            target_types=list(tool.target_types),
            arguments_schema=tool.arguments_schema,
        )
        for tool in await list_effective_tools(session, registry)
    ]


@router.put("/{tool_name}", response_model=ToolDescriptor)
async def update_tool(
    tool_name: str,
    payload: ToolDescriptorUpdate,
    session: DbSession,
    _: User = Depends(require_permission("policy:write")),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> ToolDescriptor:
    base = registry.get(tool_name)
    result = await session.execute(
        select(ToolConfiguration).where(ToolConfiguration.tool_name == tool_name)
    )
    configuration = result.scalar_one_or_none()
    target_types = list(dict.fromkeys(item.strip().lower() for item in payload.target_types if item.strip()))
    if not target_types:
        raise AppError("At least one target type is required", 422)
    if configuration is None:
        configuration = ToolConfiguration(
            tool_name=tool_name,
            description=payload.description,
            risk_level=payload.risk_level,
            target_types=target_types,
            is_enabled=True,
        )
        session.add(configuration)
    else:
        configuration.description = payload.description
        configuration.risk_level = payload.risk_level
        configuration.target_types = target_types
        configuration.is_enabled = True
    await session.flush()
    await WorkspaceBuilder(session).sync_all()
    await session.commit()
    return ToolDescriptor(
        name=base.name,
        plugin=base.plugin,
        description=configuration.description,
        risk_level=configuration.risk_level,
        target_types=configuration.target_types,
        arguments_schema=base.arguments_schema,
    )


@router.delete("/{tool_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(
    tool_name: str,
    session: DbSession,
    _: User = Depends(require_permission("policy:write")),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> Response:
    base = registry.get(tool_name)
    result = await session.execute(
        select(ToolConfiguration).where(ToolConfiguration.tool_name == tool_name)
    )
    configuration = result.scalar_one_or_none()
    if configuration is None:
        configuration = ToolConfiguration(
            tool_name=tool_name,
            description=base.description,
            risk_level=base.risk_level,
            target_types=list(base.target_types),
            is_enabled=False,
        )
        session.add(configuration)
    else:
        configuration.is_enabled = False
    await session.flush()
    await WorkspaceBuilder(session).sync_all()
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/execute", response_model=ToolExecutionResponse)
async def execute_tool(
    payload: ToolExecutionRequest,
    session: DbSession,
    user: User = Depends(require_permission("tool:execute")),
    registry: ToolRegistry = Depends(get_tool_registry),
    ssh_gateway: SshGateway = Depends(get_ssh_gateway),
) -> ToolExecutionResponse:
    server = await get_server_or_404(session, payload.server_id)
    service = OperationService(session, registry, ssh_gateway)
    result = await service.execute_tool(
        user=user,
        server=server,
        action=payload.action,
        arguments=payload.arguments,
        reason=payload.reason,
        session_id=payload.session_id,
        approval_id=payload.approval_id,
    )
    await session.commit()
    return ToolExecutionResponse(**result)


@router.post("/execute-system", response_model=list[MultiServerExecutionResult])
async def execute_system_command(
    payload: MultiServerExecutionRequest,
    session: DbSession,
    user: User = Depends(require_permission("tool:execute")),
    registry: ToolRegistry = Depends(get_tool_registry),
    ssh_gateway: SshGateway = Depends(get_ssh_gateway),
) -> list[MultiServerExecutionResult]:
    if await session.get(System, payload.system_id) is None:
        raise HTTPException(status_code=404, detail="System not found")
    targets = list((await session.scalars(
        select(Server).where(Server.system_id == payload.system_id).order_by(Server.hostname)
    )).all())
    if not targets:
        raise HTTPException(status_code=422, detail="The selected System has no servers")

    tool = await resolve_effective_tool(session, registry, "run_ssh_command")
    policy = PolicyEngine(session)
    audit = AuditService(session)
    dispatches: list[tuple[Server, str]] = []
    results: list[MultiServerExecutionResult] = []
    for target in targets:
        try:
            if not registry.supports_target(tool, target.server_type, target.os):
                raise AppError("Tool is not allowed for this server target type", 403)
            command = registry.render_command(
                "run_ssh_command", target.os, {"command": payload.command}
            )
            decision = await policy.evaluate(PolicyContext(
                user=user, server=target, action="run_ssh_command", tool=tool,
                requested_at=datetime.now(UTC),
            ))
            if decision == PolicyDecision.deny:
                await audit.record(
                    user_id=user.id, session_id=None, server_id=target.id,
                    prompt=payload.reason,
                    reasoning_summary="Policy denied multi-server execution before SSH dispatch.",
                    tool_name="run_ssh_command", ssh_command=command, output=None,
                    decision=decision, duration_ms=0, result=AuditResult.denied,
                )
                results.append(MultiServerExecutionResult(
                    server_id=target.id, hostname=target.hostname,
                    ip_address=target.ip_address, status="denied", decision="deny",
                    output="Policy denied this command.",
                ))
            elif decision == PolicyDecision.approval_required:
                approval = ApprovalRequest(
                    requested_by_user_id=user.id, server_id=target.id,
                    action="run_ssh_command", reason=payload.reason,
                    impact=f"Multi-server command on {target.hostname}",
                    plan={"kind": "multi_server_terminal", "arguments": {
                        "command": payload.command
                    }},
                )
                session.add(approval)
                await session.flush()
                await audit.record(
                    user_id=user.id, session_id=None, server_id=target.id,
                    prompt=payload.reason,
                    reasoning_summary="Policy requires approval for this batch target.",
                    tool_name="run_ssh_command", ssh_command=command, output=None,
                    decision=decision, duration_ms=0,
                    result=AuditResult.approval_required,
                )
                results.append(MultiServerExecutionResult(
                    server_id=target.id, hostname=target.hostname,
                    ip_address=target.ip_address, status="approval_required",
                    decision="approval_required", approval_id=approval.id,
                    output="Policy approval is required before execution.",
                ))
            else:
                dispatches.append((target, command))
        except AppError as exc:
            await audit.record(
                user_id=user.id, session_id=None, server_id=target.id,
                prompt=payload.reason,
                reasoning_summary="Gateway validation rejected the batch command.",
                tool_name="run_ssh_command", ssh_command=payload.command,
                output=exc.message, decision="rejected", duration_ms=0,
                result=AuditResult.failed,
            )
            results.append(MultiServerExecutionResult(
                server_id=target.id, hostname=target.hostname,
                ip_address=target.ip_address, status="failed", decision="rejected",
                output=exc.message,
            ))
    await session.commit()

    limiter = asyncio.Semaphore(payload.workers)

    async def dispatch(target: Server, command: str):
        async with limiter:
            try:
                return target, command, await ssh_gateway.execute(target, command), None
            except AppError as exc:
                return target, command, None, exc

    executed = await asyncio.gather(*(dispatch(*item) for item in dispatches))
    for target, command, command_result, error in executed:
        if error is not None:
            await audit.record(
                user_id=user.id, session_id=None, server_id=target.id,
                prompt=payload.reason,
                reasoning_summary="SSH Gateway failed multi-server command dispatch.",
                tool_name="run_ssh_command", ssh_command=command, output=error.message,
                decision=PolicyDecision.allow, duration_ms=0, result=AuditResult.failed,
            )
            results.append(MultiServerExecutionResult(
                server_id=target.id, hostname=target.hostname,
                ip_address=target.ip_address, status="failed", decision="allow",
                output=error.message,
            ))
            continue
        output = command_result.stdout or command_result.stderr or ""
        await audit.record(
            user_id=user.id, session_id=None, server_id=target.id,
            prompt=payload.reason,
            reasoning_summary="Validated batch command executed through SSH Gateway.",
            tool_name="run_ssh_command", ssh_command=command, output=output,
            decision=PolicyDecision.allow, duration_ms=command_result.duration_ms,
            exit_code=command_result.exit_code,
            result=(AuditResult.success if command_result.exit_code == 0
                    else AuditResult.failed),
        )
        results.append(MultiServerExecutionResult(
            server_id=target.id, hostname=target.hostname,
            ip_address=target.ip_address,
            status="success" if command_result.exit_code == 0 else "failed",
            decision="allow", exit_code=command_result.exit_code, output=output,
            duration_ms=command_result.duration_ms,
        ))
    await session.commit()
    order = {item.id: index for index, item in enumerate(targets)}
    return sorted(results, key=lambda item: order.get(item.server_id, len(order)))
