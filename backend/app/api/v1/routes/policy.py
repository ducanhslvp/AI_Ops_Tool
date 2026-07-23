from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.dependencies import DbSession, require_permission
from app.domain.models import ApprovalRequest, PolicyRule, Server, User
from app.core.config import get_settings
from app.schemas.operations import (
    ApprovalBulkRequest, ApprovalDecisionRequest, ApprovalOut, ApprovalWrite,
    PolicyRuleBulkRequest, PolicyRuleOut,
    PolicyRuleStatusWrite, PolicyRuleWrite,
)
from app.schemas.common import PaginationDep, set_pagination_headers
from app.services.audit_service import AuditService
from app.workspace import WorkspaceBuilder

router = APIRouter(prefix="/policy", tags=["policy"])


def _approval_upload_path(approval_id: str, filename: str) -> Path:
    safe_name = Path(filename).name
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(status_code=422, detail="Invalid attachment filename")
    root = Path(get_settings().workspace_root).resolve() / "_approval_uploads" / approval_id
    target = (root / safe_name).resolve()
    if root not in target.parents:
        raise HTTPException(status_code=422, detail="Invalid attachment path")
    return target


@router.get("/rules", response_model=list[PolicyRuleOut])
async def list_policy_rules(
    session: DbSession,
    response: Response,
    pagination: PaginationDep,
    _: User = Depends(require_permission("policy:read")),
) -> list[PolicyRuleOut]:
    total = await session.scalar(select(func.count(PolicyRule.id))) or 0
    set_pagination_headers(response, total, pagination)
    result = await session.execute(select(PolicyRule).order_by(PolicyRule.priority.asc())
                                   .offset(pagination.offset).limit(pagination.page_size))
    return [PolicyRuleOut.model_validate(item) for item in result.scalars().all()]


@router.post("/rules", response_model=PolicyRuleOut, status_code=201)
async def create_policy_rule(
    payload: PolicyRuleWrite,
    session: DbSession,
    _: User = Depends(require_permission("policy:write")),
) -> PolicyRuleOut:
    item = PolicyRule(**payload.model_dump())
    session.add(item)
    await session.flush()
    await WorkspaceBuilder(session).sync_all()
    await session.commit()
    await session.refresh(item)
    return PolicyRuleOut.model_validate(item)


@router.put("/rules/{rule_id}", response_model=PolicyRuleOut)
async def update_policy_rule(
    rule_id: str,
    payload: PolicyRuleWrite,
    session: DbSession,
    _: User = Depends(require_permission("policy:write")),
) -> PolicyRuleOut:
    item = await session.get(PolicyRule, rule_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    await session.flush()
    await WorkspaceBuilder(session).sync_all()
    await session.commit()
    await session.refresh(item)
    return PolicyRuleOut.model_validate(item)


@router.post("/rules/{rule_id}/duplicate", response_model=PolicyRuleOut, status_code=201)
async def duplicate_policy_rule(
    rule_id: str,
    session: DbSession,
    _: User = Depends(require_permission("policy:write")),
) -> PolicyRuleOut:
    source = await session.get(PolicyRule, rule_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    base_name = f"{source.name} copy"
    name = base_name
    suffix = 2
    while await session.scalar(select(PolicyRule.id).where(PolicyRule.name == name)):
        name = f"{base_name} {suffix}"
        suffix += 1
    item = PolicyRule(
        name=name, description=source.description, effect=source.effect,
        priority=source.priority, role=source.role, environment=source.environment,
        server_type=source.server_type, action=source.action, risk_level=source.risk_level,
        time_window=dict(source.time_window), is_active=False,
    )
    session.add(item)
    await session.flush()
    await WorkspaceBuilder(session).sync_all()
    await session.commit()
    await session.refresh(item)
    return PolicyRuleOut.model_validate(item)


@router.patch("/rules/{rule_id}/status", response_model=PolicyRuleOut)
async def set_policy_rule_status(
    rule_id: str,
    payload: PolicyRuleStatusWrite,
    session: DbSession,
    _: User = Depends(require_permission("policy:write")),
) -> PolicyRuleOut:
    item = await session.get(PolicyRule, rule_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    item.is_active = payload.is_active
    await session.flush()
    await WorkspaceBuilder(session).sync_all()
    await session.commit()
    await session.refresh(item)
    return PolicyRuleOut.model_validate(item)


@router.post("/rules/actions/bulk-delete")
async def bulk_delete_policy_rules(
    payload: PolicyRuleBulkRequest,
    session: DbSession,
    _: User = Depends(require_permission("policy:write")),
) -> dict[str, int]:
    unique_ids = set(payload.ids)
    items = list((await session.scalars(select(PolicyRule).where(
        PolicyRule.id.in_(unique_ids)
    ))).all())
    if len(items) != len(unique_ids):
        raise HTTPException(status_code=404, detail="One or more policy rules were not found")
    for item in items:
        await session.delete(item)
    await session.flush()
    await WorkspaceBuilder(session).sync_all()
    await session.commit()
    return {"deleted": len(items)}


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_policy_rule(
    rule_id: str,
    session: DbSession,
    _: User = Depends(require_permission("policy:write")),
) -> Response:
    item = await session.get(PolicyRule, rule_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    await session.delete(item)
    await session.flush()
    await WorkspaceBuilder(session).sync_all()
    await session.commit()
    return Response(status_code=204)


@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    session: DbSession,
    response: Response,
    pagination: PaginationDep,
    _: User = Depends(require_permission("policy:read")),
) -> list[ApprovalOut]:
    total = await session.scalar(select(func.count(ApprovalRequest.id))) or 0
    set_pagination_headers(response, total, pagination)
    result = await session.execute(
        select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
        .offset(pagination.offset).limit(pagination.page_size)
    )
    return [ApprovalOut.model_validate(item) for item in result.scalars().all()]


@router.post("/approvals", response_model=ApprovalOut, status_code=201)
async def create_approval(
    payload: ApprovalWrite,
    session: DbSession,
    requester: User = Depends(require_permission("policy:write")),
) -> ApprovalOut:
    if payload.server_id and await session.get(Server, payload.server_id) is None:
        raise HTTPException(status_code=404, detail="Server not found")
    item = ApprovalRequest(
        requested_by_user_id=requester.id, server_id=payload.server_id,
        action=payload.action, reason=payload.reason, impact=payload.impact,
        plan=payload.plan, status="pending",
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return ApprovalOut.model_validate(item)


@router.put("/approvals/{approval_id}", response_model=ApprovalOut)
async def update_approval(
    approval_id: str,
    payload: ApprovalWrite,
    session: DbSession,
    _: User = Depends(require_permission("policy:write")),
) -> ApprovalOut:
    item = await session.get(ApprovalRequest, approval_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if item.status != "pending":
        raise HTTPException(status_code=409, detail="Decided approvals cannot be edited")
    if payload.server_id and await session.get(Server, payload.server_id) is None:
        raise HTTPException(status_code=404, detail="Server not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    await session.commit()
    await session.refresh(item)
    return ApprovalOut.model_validate(item)


@router.post("/approvals/{approval_id}/attachment", response_model=ApprovalOut)
async def upload_approval_attachment(
    approval_id: str,
    session: DbSession,
    attachment: UploadFile = File(...),
    _: User = Depends(require_permission("policy:write")),
) -> ApprovalOut:
    item = await session.get(ApprovalRequest, approval_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if item.status != "pending":
        raise HTTPException(status_code=409, detail="Attachments require a pending approval")
    limit = get_settings().ssh_file_write_max_bytes
    payload = await attachment.read(limit + 1)
    if len(payload) > limit:
        raise HTTPException(status_code=413, detail="Attachment exceeds the configured limit")
    target = _approval_upload_path(approval_id, attachment.filename or "deployment.bin")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    item.plan = {
        **item.plan,
        "file_transfer": {
            "kind": "upload",
            "filename": target.name,
            "size_bytes": len(payload),
            "content_type": attachment.content_type or "application/octet-stream",
            "storage_key": target.name,
            "policy_controlled": True,
        },
    }
    await session.commit()
    await session.refresh(item)
    return ApprovalOut.model_validate(item)


@router.get("/approvals/{approval_id}/attachment")
async def download_approval_attachment(
    approval_id: str,
    session: DbSession,
    _: User = Depends(require_permission("policy:read")),
) -> FileResponse:
    item = await session.get(ApprovalRequest, approval_id)
    transfer = dict(item.plan.get("file_transfer") or {}) if item else {}
    if item is None or not transfer.get("storage_key"):
        raise HTTPException(status_code=404, detail="Approval attachment not found")
    target = _approval_upload_path(approval_id, str(transfer.get("storage_key") or ""))
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Approval attachment not found")
    return FileResponse(
        target,
        filename=target.name,
        media_type=str(transfer.get("content_type") or "application/octet-stream"),
    )


@router.post("/approvals/actions/bulk-delete")
async def bulk_delete_approvals(
    payload: ApprovalBulkRequest,
    session: DbSession,
    _: User = Depends(require_permission("policy:write")),
) -> dict[str, int]:
    ids = set(payload.ids)
    items = list((await session.scalars(select(ApprovalRequest).where(
        ApprovalRequest.id.in_(ids)))).all())
    if len(items) != len(ids):
        raise HTTPException(status_code=404, detail="One or more approvals were not found")
    for item in items:
        await session.delete(item)
    await session.commit()
    return {"deleted": len(items)}


@router.delete("/approvals/{approval_id}", status_code=204)
async def delete_approval(
    approval_id: str,
    session: DbSession,
    _: User = Depends(require_permission("policy:write")),
) -> Response:
    item = await session.get(ApprovalRequest, approval_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    await session.delete(item)
    await session.commit()
    return Response(status_code=204)


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalOut)
async def decide_approval(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    session: DbSession,
    approver: User = Depends(require_permission("approval:decide")),
) -> ApprovalOut:
    approval = await session.get(ApprovalRequest, approval_id, with_for_update=True)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval already decided")
    if approval.requested_by_user_id == approver.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Self-approval is forbidden"
        )
    approval.status = payload.decision
    approval.decided_by_user_id = approver.id
    approval.decided_at = datetime.now(UTC)
    approval.plan = {**approval.plan, "decision_comment": payload.comment}
    await AuditService(session).record(
        user_id=approver.id,
        session_id=None,
        server_id=approval.server_id,
        prompt=payload.comment,
        reasoning_summary="Human approval decision recorded.",
        tool_name=approval.action,
        ssh_command=None,
        output=None,
        decision=payload.decision,
        duration_ms=0,
        result="success",
    )
    await session.commit()
    await session.refresh(approval)
    return ApprovalOut.model_validate(approval)
