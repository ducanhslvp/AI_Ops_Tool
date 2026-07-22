import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, or_, select

from app.api.dependencies import DbSession, require_permission
from app.domain.models import AuditLog, Server, User
from app.services.audit_service import AuditService
from app.schemas.common import PaginationDep, set_pagination_headers

router = APIRouter(prefix="/audit", tags=["audit"])


def _safe_csv(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


def _statement(q: str, user_id: str | None, server_id: str | None, tool: str | None,
               result: str | None, date_from: datetime | None, date_to: datetime | None):
    statement = select(AuditLog, User.email, Server.hostname).outerjoin(
        User, User.id == AuditLog.user_id).outerjoin(Server, Server.id == AuditLog.server_id)
    if q:
        statement = statement.where(or_(User.email.ilike(f"%{q}%"),
                                        Server.hostname.ilike(f"%{q}%"),
                                        AuditLog.tool_name.ilike(f"%{q}%"),
                                        AuditLog.prompt.ilike(f"%{q}%"),
                                        AuditLog.output.ilike(f"%{q}%")))
    if user_id:
        statement = statement.where(AuditLog.user_id == user_id)
    if server_id:
        statement = statement.where(AuditLog.server_id == server_id)
    if tool:
        statement = statement.where(AuditLog.tool_name == tool)
    if result:
        statement = statement.where(AuditLog.result == result)
    if date_from:
        statement = statement.where(AuditLog.created_at >= date_from)
    if date_to:
        statement = statement.where(AuditLog.created_at <= date_to)
    return statement


def _serialize(row) -> dict:
    item, email, hostname = row
    return {
        "id": item.id, "created_at": item.created_at, "user_id": item.user_id,
        "user_email": email, "server_id": item.server_id, "server_hostname": hostname,
        "session_id": item.session_id, "tool_name": item.tool_name,
        "decision": item.decision, "duration_ms": item.duration_ms, "result": item.result,
        "exit_code": item.exit_code, "approval_used": item.approval_used,
        "prompt_preview": (item.prompt or "")[:180],
        "output_preview": (item.output or "")[:180],
        "provider": item.provider, "model": item.model, "request_id": item.request_id,
        "ssh_command": item.ssh_command,
        "integrity_hash": item.integrity_hash,
    }


@router.get("")
async def list_audit(
    session: DbSession,
    response: Response,
    pagination: PaginationDep,
    _: User = Depends(require_permission("audit:read")),
    q: str = "",
    user_id: str | None = None,
    server_id: str | None = None,
    tool: str | None = None,
    result: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    statement = _statement(q, user_id, server_id, tool, result, date_from, date_to)
    total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    set_pagination_headers(response, total or 0, pagination)
    rows = (await session.execute(statement.order_by(AuditLog.created_at.desc())
                                  .offset(pagination.offset).limit(pagination.page_size))).all()
    return [_serialize(row) for row in rows]


@router.get("/export")
async def export_audit(
    session: DbSession,
    _: User = Depends(require_permission("audit:read")),
    q: str = "",
    tool: str | None = None,
    result: str | None = None,
) -> Response:
    rows = (await session.execute(_statement(q, None, None, tool, result, None, None)
                                  .order_by(AuditLog.created_at.desc()).limit(10_000))).all()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    fields = ["created_at", "user_email", "server_hostname", "tool_name", "decision",
              "duration_ms", "result", "integrity_hash"]
    writer.writerow(fields)
    for row in rows:
        record = _serialize(row)
        writer.writerow([_safe_csv(record[field]) for field in fields])
    return Response(output.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=audit.csv"})


@router.get("/integrity")
async def verify_audit_integrity(
    session: DbSession,
    _: User = Depends(require_permission("audit:read")),
) -> dict:
    valid, records = await AuditService(session).verify_chain()
    return {"valid": valid, "records_verified": records}


@router.get("/{audit_id}")
async def get_audit_detail(
    audit_id: str,
    session: DbSession,
    _: User = Depends(require_permission("audit:read")),
) -> dict:
    row = (await session.execute(select(AuditLog, User.email, Server.hostname)
        .outerjoin(User, User.id == AuditLog.user_id)
        .outerjoin(Server, Server.id == AuditLog.server_id)
        .where(AuditLog.id == audit_id))).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit record not found")
    item = row[0]
    return {**_serialize(row), "prompt": item.prompt, "provider_input": item.provider_input,
            "context_sources": item.context_sources, "tool_events": item.tool_events,
            "reasoning_summary": item.reasoning_summary, "ssh_command": item.ssh_command,
            "output": item.output}
