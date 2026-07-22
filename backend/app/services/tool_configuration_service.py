from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.domain.models import ToolConfiguration
from app.services.tool_registry import ToolDescriptorInternal, ToolRegistry


async def list_effective_tools(
    session: AsyncSession, registry: ToolRegistry
) -> list[ToolDescriptorInternal]:
    result = await session.execute(select(ToolConfiguration))
    configurations = {item.tool_name: item for item in result.scalars().all()}
    tools: list[ToolDescriptorInternal] = []
    for base in registry.all():
        configuration = configurations.get(base.name)
        if configuration is not None and not configuration.is_enabled:
            continue
        tools.append(_apply_configuration(base, configuration))
    return tools


async def resolve_effective_tool(
    session: AsyncSession, registry: ToolRegistry, name: str
) -> ToolDescriptorInternal:
    base = registry.get(name)
    result = await session.execute(
        select(ToolConfiguration).where(ToolConfiguration.tool_name == name)
    )
    configuration = result.scalar_one_or_none()
    if configuration is not None and not configuration.is_enabled:
        raise AppError(f"Tool action is disabled: {name}", 404)
    return _apply_configuration(base, configuration)


def _apply_configuration(
    base: ToolDescriptorInternal, configuration: ToolConfiguration | None
) -> ToolDescriptorInternal:
    if configuration is None:
        return base
    return replace(
        base,
        description=configuration.description,
        risk_level=configuration.risk_level,
        target_types=tuple(configuration.target_types),
    )
