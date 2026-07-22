from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import DiscoverySchedule, User
from app.services.discovery_service import DiscoveryService
from app.services.ssh_gateway import SshGateway
from app.services.tool_registry import ToolRegistry


async def run_due_discovery_schedules(
    session: AsyncSession, registry: ToolRegistry, gateway: SshGateway, limit: int = 10
) -> int:
    schedules = list((await session.scalars(select(DiscoverySchedule).where(
        DiscoverySchedule.enabled.is_(True), DiscoverySchedule.next_run_at <= datetime.now(UTC)
    ).order_by(DiscoverySchedule.next_run_at).limit(limit))).all())
    completed = 0
    for schedule in schedules:
        user = await session.get(User, schedule.requested_by_user_id)
        if user is None or not user.is_active:
            schedule.enabled = False
            continue
        await DiscoveryService(session, registry, gateway).run_schedule(schedule, user)
        completed += 1
    await session.commit()
    return completed
