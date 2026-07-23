from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select

from app.api.dependencies import (
    DbSession, get_gateway, get_ssh_gateway, get_tool_registry, require_permission,
)
from app.ai.gateway import AIGateway
from app.domain.models import DiscoveryScan, DiscoverySchedule, System, User
from app.schemas.common import PaginationDep, set_pagination_headers
from app.schemas.discovery import (
    DiscoveryCreate, DiscoveryScanOut, DiscoveryScheduleOut, DiscoveryScheduleWrite,
)
from app.services.discovery_service import DiscoveryService
from app.services.ssh_gateway import SshGateway
from app.services.tool_registry import ToolRegistry

router = APIRouter(prefix="/discovery", tags=["discovery"])


async def _scan_or_404(session: DbSession, scan_id: str) -> DiscoveryScan:
    scan = await session.get(DiscoveryScan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Discovery scan not found")
    return scan


async def _schedule_or_404(session: DbSession, schedule_id: str) -> DiscoverySchedule:
    schedule = await session.get(DiscoverySchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Discovery schedule not found")
    return schedule


@router.get("/scans", response_model=list[DiscoveryScanOut])
async def list_scans(session: DbSession, response: Response, pagination: PaginationDep,
                     _: User = Depends(require_permission("inventory:read")),
                     system_id: str | None = None) -> list[DiscoveryScan]:
    statement = select(DiscoveryScan).order_by(DiscoveryScan.created_at.desc())
    if system_id:
        statement = statement.where(DiscoveryScan.system_id == system_id)
    total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    set_pagination_headers(response, total or 0, pagination)
    return list((await session.scalars(statement.offset(pagination.offset).limit(
        pagination.page_size))).all())


@router.post("/scans", response_model=DiscoveryScanOut, status_code=201)
async def create_scan(
    payload: DiscoveryCreate,
    session: DbSession,
    user: User = Depends(require_permission("tool:execute")),
    registry: ToolRegistry = Depends(get_tool_registry),
    gateway: SshGateway = Depends(get_ssh_gateway),
    ai_gateway: AIGateway = Depends(get_gateway),
) -> DiscoveryScan:
    return await DiscoveryService(session, registry, gateway, ai_gateway).run(payload, user)


@router.get("/scans/{scan_id}", response_model=DiscoveryScanOut)
async def get_scan(scan_id: str, session: DbSession,
                   _: User = Depends(require_permission("inventory:read"))) -> DiscoveryScan:
    return await _scan_or_404(session, scan_id)


@router.get("/scans/{scan_id}/evidence")
async def get_scan_evidence(scan_id: str, session: DbSession,
                            _: User = Depends(require_permission("audit:read"))) -> dict:
    scan = await _scan_or_404(session, scan_id)
    return {"scan_id": scan.id, "evidence": scan.raw_evidence}


@router.get("/schedules", response_model=list[DiscoveryScheduleOut])
async def list_schedules(session: DbSession,
                         _: User = Depends(require_permission("inventory:read"))) -> list[DiscoverySchedule]:
    return list((await session.scalars(select(DiscoverySchedule).order_by(
        DiscoverySchedule.name))).all())


@router.post("/schedules", response_model=DiscoveryScheduleOut, status_code=201)
async def create_schedule(payload: DiscoveryScheduleWrite, session: DbSession,
                          user: User = Depends(require_permission("inventory:write"))) -> DiscoverySchedule:
    if payload.system_id and await session.get(System, payload.system_id) is None:
        raise HTTPException(status_code=422, detail="System does not exist")
    item = DiscoverySchedule(**payload.model_dump(), requested_by_user_id=user.id,
                             next_run_at=datetime.now(UTC) + timedelta(
                                 minutes=payload.interval_minutes))
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.put("/schedules/{schedule_id}", response_model=DiscoveryScheduleOut)
async def update_schedule(schedule_id: str, payload: DiscoveryScheduleWrite, session: DbSession,
                          _: User = Depends(require_permission("inventory:write"))) -> DiscoverySchedule:
    item = await _schedule_or_404(session, schedule_id)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    item.next_run_at = datetime.now(UTC) + timedelta(minutes=item.interval_minutes)
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: str, session: DbSession,
                          _: User = Depends(require_permission("inventory:write"))) -> Response:
    await session.delete(await _schedule_or_404(session, schedule_id))
    await session.commit()
    return Response(status_code=204)


@router.post("/schedules/{schedule_id}/run", response_model=DiscoveryScanOut)
async def run_schedule(
    schedule_id: str,
    session: DbSession,
    user: User = Depends(require_permission("tool:execute")),
    registry: ToolRegistry = Depends(get_tool_registry),
    gateway: SshGateway = Depends(get_ssh_gateway),
    ai_gateway: AIGateway = Depends(get_gateway),
) -> DiscoveryScan:
    schedule = await _schedule_or_404(session, schedule_id)
    return await DiscoveryService(
        session, registry, gateway, ai_gateway).run_schedule(schedule, user)
