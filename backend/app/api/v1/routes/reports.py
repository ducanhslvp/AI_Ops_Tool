import csv
import html
import io
from difflib import unified_diff

from fastapi import APIRouter, Depends, HTTPException, Response, status
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import func, select

from app.api.dependencies import DbSession, require_permission
from app.domain.models import Alert, AuditLog, Report, ReportTemplate, Server, System, User
from app.schemas.reports import ReportCreate, ReportOut, ReportUpdate
from app.schemas.common import PaginationDep, set_pagination_headers
from app.workspace import WorkspaceBuilder

router = APIRouter(prefix="/reports", tags=["reports"])


async def get_report_or_404(session: DbSession, report_id: str) -> Report:
    report = await session.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


async def _evidence(session: DbSession, system_id: str | None, server_id: str | None = None) -> dict:
    system = await session.get(System, system_id) if system_id else None
    if system_id and system is None:
        raise HTTPException(status_code=422, detail="System does not exist")
    server_statement = select(func.count(Server.id))
    online_statement = select(func.count(Server.id)).where(Server.status == "online")
    alert_statement = select(func.count(Alert.id)).where(Alert.status == "open")
    audit_statement = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(25)
    target = await session.get(Server, server_id) if server_id else None
    if server_id and target is None:
        raise HTTPException(status_code=422, detail="Server does not exist")
    if target and system_id and target.system_id != system_id:
        raise HTTPException(status_code=422, detail="Server does not belong to the selected System")
    if system_id:
        server_statement = server_statement.where(Server.system_id == system_id)
        online_statement = online_statement.where(Server.system_id == system_id)
        alert_statement = alert_statement.where(Alert.system_id == system_id)
        audit_statement = audit_statement.join(Server, Server.id == AuditLog.server_id).where(
            Server.system_id == system_id)
    if target:
        server_statement = select(func.count(Server.id)).where(Server.id == target.id)
        online_statement = select(func.count(Server.id)).where(
            Server.id == target.id, Server.status == "online"
        )
        audit_statement = select(AuditLog).where(AuditLog.server_id == target.id).order_by(
            AuditLog.created_at.desc()
        ).limit(25)
        alert_statement = select(func.count(Alert.id)).where(
            Alert.server_id == target.id, Alert.status == "open"
        )
    servers = await session.scalar(server_statement) or 0
    online = await session.scalar(online_statement) or 0
    alerts = await session.scalar(alert_statement) or 0
    audits = list((await session.scalars(audit_statement)).all())
    return {"system": system.name if system else "Platform", "servers": servers,
            "online": online, "alerts": alerts, "audits": audits,
            "target": f"{target.hostname} ({target.ip_address})" if target else None}


def _default_content(data: dict, output_format: str) -> str:
    rows = [{"timestamp": item.created_at.isoformat(), "tool": item.tool_name or "-",
             "decision": item.decision or "-", "result": item.result,
             "duration_ms": item.duration_ms} for item in data["audits"]]
    if output_format == "csv":
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=["timestamp", "tool", "decision", "result",
                                                       "duration_ms"])
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()
    summary = (f"System: {data['system']}\nTarget: {data['target'] or 'All servers'}\nServers: {data['servers']}\n"
               f"Online: {data['online']}\nOpen alerts: {data['alerts']}")
    timeline = "\n".join(f"- {row['timestamp']} | {row['tool']} | {row['decision']} | "
                           f"{row['result']} | {row['duration_ms']} ms" for row in rows)
    if output_format == "html":
        items = "".join(
            "<tr>" + "".join(
                f"<td>{html.escape(str(value))}</td>" for value in row.values()
            ) + "</tr>"
            for row in rows
        )
        return (f"<!doctype html><html><body><h1>Operations report: "
                f"{html.escape(data['system'])}</h1><pre>{html.escape(summary)}</pre>"
                f"<table><tbody>{items}</tbody></table></body></html>")
    return f"# Operations report: {data['system']}\n\n{summary}\n\n## Audit evidence\n\n{timeline}"


def _pdf(content: str) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    y = height - 48
    for raw_line in content.splitlines():
        line = raw_line[:120]
        if y < 48:
            document.showPage()
            y = height - 48
        document.drawString(48, y, line)
        y -= 14
    document.save()
    return output.getvalue()


@router.get("")
async def list_reports(
    session: DbSession,
    response: Response,
    pagination: PaginationDep,
    _: User = Depends(require_permission("report:read")),
    q: str = "",
    format: str | None = None,
    system_id: str | None = None,
    server_id: str | None = None,
) -> list[dict]:
    statement = select(Report).order_by(Report.created_at.desc())
    if q:
        statement = statement.where(Report.title.ilike(f"%{q}%"))
    if format:
        statement = statement.where(Report.format == format)
    if system_id:
        statement = statement.where(Report.system_id == system_id)
    if server_id:
        statement = statement.where(Report.server_id == server_id)
    total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    set_pagination_headers(response, total or 0, pagination)
    reports = (await session.scalars(statement.offset(pagination.offset).limit(
        pagination.page_size))).all()
    return [{"id": report.id, "title": report.title, "format": report.format,
             "system_id": report.system_id, "server_id": report.server_id,
             "created_at": report.created_at,
             "updated_at": report.updated_at} for report in reports]


@router.get("/templates")
async def list_report_templates(
    session: DbSession,
    _: User = Depends(require_permission("report:read")),
) -> list[dict]:
    templates = (
        await session.scalars(
            select(ReportTemplate)
            .where(ReportTemplate.is_active.is_(True))
            .order_by(ReportTemplate.name)
        )
    ).all()
    return [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "format": item.format,
        }
        for item in templates
    ]


@router.post("", response_model=ReportOut, status_code=201)
async def create_report(payload: ReportCreate, session: DbSession,
                        user: User = Depends(require_permission("report:write"))) -> ReportOut:
    evidence = await _evidence(session, payload.system_id, payload.server_id)
    content = _default_content(evidence, payload.format)
    if payload.template_id:
        template = await session.get(ReportTemplate, payload.template_id)
        if template is None or not template.is_active:
            raise HTTPException(status_code=422, detail="Report template is unavailable")
        try:
            content = template.template_body.format_map({
                "system": evidence["system"], "servers": evidence["servers"],
                "online": evidence["online"], "alerts": evidence["alerts"],
                "evidence": content,
            })
        except KeyError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Report template contains unsupported placeholder: {exc.args[0]}",
            ) from exc
    report = Report(system_id=payload.system_id, server_id=payload.server_id,
                    title=payload.title, format=payload.format,
                    content=content, generated_by_user_id=user.id)
    session.add(report)
    await session.flush()
    if report.system_id:
        await WorkspaceBuilder(session).sync_system(report.system_id)
    await session.commit()
    await session.refresh(report)
    return ReportOut.model_validate(report)


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: str, session: DbSession,
                     _: User = Depends(require_permission("report:read"))) -> Report:
    return await get_report_or_404(session, report_id)


@router.put("/{report_id}", response_model=ReportOut)
async def update_report(report_id: str, payload: ReportUpdate, session: DbSession,
                        _: User = Depends(require_permission("report:write"))) -> Report:
    report = await get_report_or_404(session, report_id)
    report.title = payload.title
    await session.flush()
    if report.system_id:
        await WorkspaceBuilder(session).sync_system(report.system_id)
    await session.commit()
    await session.refresh(report)
    return report


@router.delete("/{report_id}", status_code=204)
async def delete_report(report_id: str, session: DbSession,
                        _: User = Depends(require_permission("report:write"))) -> Response:
    report = await get_report_or_404(session, report_id)
    system_id = report.system_id
    await session.delete(report)
    await session.flush()
    if system_id:
        await WorkspaceBuilder(session).sync_system(system_id)
    await session.commit()
    return Response(status_code=204)


@router.get("/{report_id}/download")
async def download_report(report_id: str, session: DbSession,
                          _: User = Depends(require_permission("report:read"))) -> Response:
    report = await get_report_or_404(session, report_id)
    extension = {"markdown": "md", "html": "html", "pdf": "pdf", "csv": "csv"}[report.format]
    content = _pdf(report.content) if report.format == "pdf" else report.content.encode("utf-8")
    media_type = {"markdown": "text/markdown", "html": "text/html", "pdf": "application/pdf",
                  "csv": "text/csv"}[report.format]
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="report-{report.id}.{extension}"'})


@router.get("/{report_id}/compare-latest")
async def compare_report_with_previous(report_id: str, session: DbSession,
                                        _: User = Depends(require_permission("report:read"))) -> dict:
    report = await get_report_or_404(session, report_id)
    previous = await session.scalar(select(Report).where(
        Report.system_id == report.system_id, Report.id != report.id,
        Report.created_at < report.created_at).order_by(Report.created_at.desc()).limit(1))
    if previous is None:
        return {"previous_report_id": None, "diff": "No previous report is available."}
    diff = "\n".join(unified_diff(previous.content.splitlines(), report.content.splitlines(),
                                  fromfile=previous.title, tofile=report.title, lineterm=""))
    return {"previous_report_id": previous.id, "diff": diff or "No content changes."}
