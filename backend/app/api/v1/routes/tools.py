from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from app.api.dependencies import (
    DbSession,
    get_server_or_404,
    get_ssh_gateway,
    get_tool_registry,
    require_permission,
)
from app.domain.models import ToolConfiguration, User
from app.core.exceptions import AppError
from app.schemas.operations import (
    ToolDescriptor,
    ToolDescriptorUpdate,
    ToolExecutionRequest,
    ToolExecutionResponse,
)
from app.services.operation_service import OperationService
from app.services.ssh_gateway import SshGateway
from app.services.tool_registry import ToolRegistry
from app.services.tool_configuration_service import list_effective_tools
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
