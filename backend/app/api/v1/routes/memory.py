from datetime import UTC, datetime

import asyncio
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.dependencies import DbSession, get_gateway, require_permission
from app.ai.gateway import AIGateway
from app.domain.models import AiMemory, AiSession, KnowledgeDocument, System, User
from app.schemas.common import PaginationDep, set_pagination_headers
from app.schemas.memory import (
    AiMemoryOut, AiSessionStatusOut, MemoryCompareOut, MemoryCompareRequest,
    MemoryExportOut, MemoryMaintenanceOut, MemoryMaintenanceRequest,
)
from app.services.memory_service import MemoryService
from app.workspace import WorkspaceBuilder

router = APIRouter(prefix="/ai/systems/{system_id}", tags=["ai-memory"])
PROTECTED_WORKSPACE_FILES = {
    ".workspace-manifest.json", "README.md", "servers.yaml", "policy.yaml", "tools.md",
    "system_prompt.md", "inventory.md", "architecture.md", "topology.md",
    "dependencies.md", "services.md",
}


async def _system(session: DbSession, system_id: str) -> System:
    system = await session.get(System, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail="System not found")
    return system


def _confirm(system: System, payload: MemoryMaintenanceRequest) -> None:
    if payload.confirm_system_code != system.code:
        raise HTTPException(status_code=409, detail="System confirmation code does not match")


@router.get("/session-status", response_model=AiSessionStatusOut)
async def session_status(
    system_id: str, session: DbSession, gateway: AIGateway = Depends(get_gateway),
    _: User = Depends(require_permission("ai:chat")),
) -> AiSessionStatusOut:
    system = await _system(session, system_id)
    latest = await session.scalar(
        select(AiSession).where(AiSession.system_id == system.id)
        .order_by(AiSession.last_activity_at.desc()).limit(1)
    )
    active = await session.scalar(select(func.count(AiSession.id)).where(
        AiSession.system_id == system.id)) or 0
    health = await gateway.manager.active.health_check()
    workspace = WorkspaceBuilder(session)
    if not workspace.workspace_path(system).is_dir():
        await workspace.sync_system(system.id)
    return AiSessionStatusOut(
        system_id=system.id, provider=gateway.manager.active_name,
        status=latest.status if latest else "idle", connected=health.status.value == "ready",
        last_activity=latest.last_activity_at if latest else None,
        workspace_path=str(workspace.workspace_path(system)),
        context_size=latest.context_size if latest else 0,
        memory_size=await MemoryService(session, workspace).size(system),
        active_conversations=active,
    )


@router.get("/workspace")
async def workspace_overview(
    system_id: str, session: DbSession,
    _: User = Depends(require_permission("ai:chat")),
) -> dict:
    system = await _system(session, system_id)
    workspace = WorkspaceBuilder(session)
    root = workspace.workspace_path(system)
    if not root.is_dir():
        await workspace.sync_system(system.id)
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            relative = path.relative_to(root).as_posix()
            if any(part.casefold() in {"secrets", "credentials"} for part in path.parts):
                continue
            managed = path.name in PROTECTED_WORKSPACE_FILES or path.parent.name in {
                "generated", "discovery", "inventory", "context", "reports", "skills"
            }
            files.append({"path": relative, "size": path.stat().st_size,
                          "deletable": not managed})
    memories = list((await session.scalars(
        select(AiMemory).where(AiMemory.system_id == system.id,
                               AiMemory.archived_at.is_(None))
        .order_by(AiMemory.occurred_at.desc()).limit(20)
    )).all())
    return {
        "system": {"id": system.id, "code": system.code, "name": system.name},
        "workspace_path": str(root), "file_count": len(files), "files": files[:500],
        "memory_count": await session.scalar(select(func.count(AiMemory.id)).where(
            AiMemory.system_id == system.id, AiMemory.archived_at.is_(None))) or 0,
        "memories": [{"id": item.id, "category": item.category, "topic": item.topic,
                      "summary": item.summary, "occurred_at": item.occurred_at}
                     for item in memories],
    }


def _workspace_file(workspace: WorkspaceBuilder, system: System, relative_path: str) -> Path:
    normalized = PurePosixPath(relative_path.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts or not normalized.parts:
        raise HTTPException(status_code=422, detail="Invalid workspace file path")
    if any(part.casefold() in {"secrets", "credentials"} for part in normalized.parts):
        raise HTTPException(status_code=403, detail="Sensitive workspace paths are not accessible")
    root = workspace.workspace_path(system).resolve()
    candidate = (root / Path(*normalized.parts)).resolve()
    if root not in candidate.parents or not candidate.is_file() or candidate.is_symlink():
        raise HTTPException(status_code=404, detail="Workspace file not found")
    return candidate


@router.get("/workspace/file/preview")
async def preview_workspace_file(
    system_id: str, path: str, session: DbSession,
    _: User = Depends(require_permission("ai:chat")),
) -> dict:
    system = await _system(session, system_id)
    workspace = WorkspaceBuilder(session)
    source = _workspace_file(workspace, system, path)
    previewable = source.suffix.casefold() in {
        ".md", ".txt", ".yaml", ".yml", ".json", ".log", ".csv", ".py", ".sh", ".ps1",
    }
    if not previewable:
        return {"path": path, "previewable": False, "content": "", "size": source.stat().st_size}
    content = await asyncio.to_thread(source.read_text, encoding="utf-8", errors="replace")
    truncated = len(content) > 500_000
    return {"path": path, "previewable": True, "content": content[:500_000],
            "truncated": truncated, "size": source.stat().st_size}


@router.get("/workspace/file/download")
async def download_workspace_file(
    system_id: str, path: str, session: DbSession,
    _: User = Depends(require_permission("ai:chat")),
):
    system = await _system(session, system_id)
    source = _workspace_file(WorkspaceBuilder(session), system, path)
    return FileResponse(source, filename=source.name, media_type="application/octet-stream")


@router.delete("/workspace/file", status_code=204)
async def delete_workspace_file(
    system_id: str, path: str, session: DbSession,
    _: User = Depends(require_permission("ai:chat")),
) -> Response:
    system = await _system(session, system_id)
    workspace = WorkspaceBuilder(session)
    source = _workspace_file(workspace, system, path)
    relative = source.relative_to(workspace.storage.root).as_posix()
    if source.name in PROTECTED_WORKSPACE_FILES or source.parts[-2] in {
        "generated", "discovery", "inventory", "context", "reports", "skills"
    }:
        raise HTTPException(status_code=409, detail="This file is managed by Workspace Builder")
    document = await session.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.system_id == system.id,
        KnowledgeDocument.source_uri == f"workspace://{relative}",
    ))
    memory = await session.scalar(select(AiMemory).where(
        AiMemory.system_id == system.id, AiMemory.file_path == relative,
    ))
    if document:
        await workspace.remove_document_files(document)
        await session.delete(document)
    elif memory:
        await workspace.storage.remove(relative)
        await session.delete(memory)
    else:
        await workspace.storage.remove(relative)
    await session.commit()
    return Response(status_code=204)


@router.post("/workspace/refresh")
async def refresh_workspace(
    system_id: str, session: DbSession,
    user: User = Depends(require_permission("ai:chat")),
) -> dict:
    system = await _system(session, system_id)
    workspace = WorkspaceBuilder(session)
    await workspace.sync_system(system.id)
    conversations = list((await session.scalars(select(AiSession).where(
        AiSession.system_id == system.id, AiSession.user_id == user.id
    ))).all())
    for conversation in conversations:
        memory = dict(conversation.memory or {})
        memory["workspace_reload_required"] = True
        conversation.memory = memory
    await session.commit()
    return {"system_id": system.id, "refreshed": True,
            "sessions_marked_for_reload": len(conversations)}


@router.get("/memories", response_model=list[AiMemoryOut])
async def memories(
    system_id: str, session: DbSession, response: Response, pagination: PaginationDep,
    query: str | None = Query(None, max_length=200),
    category: str | None = Query(None, max_length=40), archived: bool = False,
    _: User = Depends(require_permission("ai:chat")),
) -> list[AiMemoryOut]:
    await _system(session, system_id)
    items, total = await MemoryService(session).list(
        system_id, query=query, category=category, archived=archived,
        offset=pagination.offset, limit=pagination.page_size,
    )
    set_pagination_headers(response, total, pagination)
    return [AiMemoryOut.model_validate(item) for item in items]


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(
    system_id: str, memory_id: str, session: DbSession,
    _: User = Depends(require_permission("ai:chat")),
) -> Response:
    system = await _system(session, system_id)
    memory = await session.get(AiMemory, memory_id)
    if memory is None or memory.system_id != system.id:
        raise HTTPException(status_code=404, detail="Memory record not found in this System")
    workspace = WorkspaceBuilder(session)
    try:
        await workspace.storage.remove(memory.file_path)
    except ValueError:
        raise HTTPException(status_code=422, detail="Memory file path is invalid") from None
    await session.delete(memory)
    conversations = list((await session.scalars(select(AiSession).where(
        AiSession.system_id == system.id
    ))).all())
    for conversation in conversations:
        conversation.provider_session_id = None
        conversation.memory = {**(conversation.memory or {}), "workspace_reload_required": True}
    await session.commit()
    return Response(status_code=204)


@router.post("/memories/compare", response_model=MemoryCompareOut)
async def compare_memory(
    system_id: str, payload: MemoryCompareRequest, session: DbSession,
    _: User = Depends(require_permission("ai:chat")),
) -> MemoryCompareOut:
    left = await session.get(AiMemory, payload.left_id)
    right = await session.get(AiMemory, payload.right_id)
    if not left or not right or left.system_id != system_id or right.system_id != system_id:
        raise HTTPException(status_code=404, detail="Memory record not found in this system")
    return MemoryCompareOut(left=AiMemoryOut.model_validate(left),
                            right=AiMemoryOut.model_validate(right),
                            diff=MemoryService.compare(left, right))


@router.get("/memories/export", response_model=MemoryExportOut)
async def export_memory(
    system_id: str, session: DbSession,
    _: User = Depends(require_permission("ai:chat")),
) -> MemoryExportOut:
    system = await _system(session, system_id)
    items, _ = await MemoryService(session).list(
        system.id, query=None, category=None, archived=False, offset=0, limit=5000)
    lines = [f"# AI Memory Export: {system.name}", "", f"Generated: `{datetime.now(UTC).isoformat()}`", ""]
    for item in items:
        lines.extend([f"## {item.topic}", "", f"- Category: `{item.category}`",
                      f"- Occurred: `{item.occurred_at.isoformat()}`", "", item.summary, ""])
    return MemoryExportOut(filename=f"{system.code.lower()}-ai-memory.md", markdown="\n".join(lines))


async def _maintain(system_id: str, payload: MemoryMaintenanceRequest, session: DbSession,
                    operation: str) -> MemoryMaintenanceOut:
    system = await _system(session, system_id)
    _confirm(system, payload)
    service = MemoryService(session)
    if operation == "reset-conversations":
        count = await service.reset_conversations(system)
        detail = "Conversation history was removed; knowledge and AI memory were preserved."
    elif operation == "reset-memory":
        count = await service.reset_memory(system)
        detail = "Learned AI memory was removed; source knowledge was preserved."
    elif operation == "refresh-memory":
        count = await service.refresh_memory(system)
        detail = "Memory was deterministically rebuilt from retained conversations."
    elif operation == "refresh-knowledge":
        count = await service.refresh_knowledge(system)
        detail = "Knowledge projections were regenerated from original uploads and inventory."
    elif operation == "rebuild-workspace":
        count = await service.refresh_knowledge(system)
        detail = "Generated workspace files were rebuilt without deleting user sources."
    elif operation == "archive-memory":
        count = await service.archive(system)
        detail = "Active memory was archived and excluded from default context selection."
    else:
        raise HTTPException(status_code=400, detail="Unsupported maintenance operation")
    await session.commit()
    return MemoryMaintenanceOut(operation=operation, system_id=system.id,
                                affected_records=count, detail=detail)


@router.post("/{operation}", response_model=MemoryMaintenanceOut)
async def maintain(
    system_id: str, operation: str, payload: MemoryMaintenanceRequest, session: DbSession,
    _: User = Depends(require_permission("ai:chat")),
) -> MemoryMaintenanceOut:
    allowed = {"reset-conversations", "reset-memory", "refresh-memory", "refresh-knowledge",
               "rebuild-workspace", "archive-memory"}
    if operation not in allowed:
        raise HTTPException(status_code=404, detail="Maintenance operation not found")
    return await _maintain(system_id, payload, session, operation)
