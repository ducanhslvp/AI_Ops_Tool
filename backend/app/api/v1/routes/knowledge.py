import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import func, or_, select

from app.api.dependencies import DbSession, require_permission
from app.domain.models import KnowledgeDocument, System, User
from app.schemas.knowledge import KnowledgeOut, KnowledgeWrite
from app.schemas.common import PaginationDep, set_pagination_headers
from app.workspace import WorkspaceBuilder
from app.services.document_extractor import extract_document

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
LEGACY_STORAGE = Path(__file__).resolve().parents[4] / "data" / "knowledge"
ALLOWED_TYPES = {".pdf": "pdf", ".docx": "docx", ".md": "markdown", ".txt": "txt"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


async def _get(session: DbSession, item_id: str) -> KnowledgeDocument:
    item = await session.get(KnowledgeDocument, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    return item


@router.get("", response_model=list[KnowledgeOut])
async def list_knowledge(session: DbSession, response: Response,
                         pagination: PaginationDep,
                         _: User = Depends(require_permission("inventory:read")),
                         q: str = "", system_id: str | None = None):
    statement = select(KnowledgeDocument).order_by(KnowledgeDocument.updated_at.desc())
    if q:
        statement = statement.where(or_(KnowledgeDocument.title.ilike(f"%{q}%"),
                                        KnowledgeDocument.content_text.ilike(f"%{q}%")))
    if system_id:
        statement = statement.where(KnowledgeDocument.system_id == system_id)
    total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    set_pagination_headers(response, total or 0, pagination)
    return list((await session.scalars(statement.offset(pagination.offset).limit(
        pagination.page_size))).all())


@router.post("", response_model=KnowledgeOut, status_code=201)
async def create_knowledge(payload: KnowledgeWrite, session: DbSession,
                           _: User = Depends(require_permission("inventory:write"))):
    system = await session.get(System, payload.system_id)
    if system is None:
        raise HTTPException(status_code=422, detail="System does not exist")
    item = KnowledgeDocument(**payload.model_dump(), source_uri="")
    session.add(item)
    await session.flush()
    await WorkspaceBuilder(session).sync_system(system.id)
    await session.commit()
    await session.refresh(item)
    return item


@router.post("/upload", response_model=KnowledgeOut, status_code=201)
async def upload_knowledge(
    session: DbSession,
    _: User = Depends(require_permission("inventory:write")),
    system_id: str = Form(...),
    title: str = Form(..., min_length=2, max_length=200),
    file: UploadFile = File(...),
):
    system = await session.get(System, system_id)
    if system is None:
        raise HTTPException(status_code=422, detail="System does not exist")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Only PDF, DOCX, Markdown and TXT are supported")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Knowledge file exceeds 20 MB")
    try:
        content = await asyncio.to_thread(extract_document, data, suffix)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Document content could not be extracted") from exc
    item = KnowledgeDocument(system_id=system_id, title=title,
                             document_type=ALLOWED_TYPES[suffix], source_uri="",
                             content_text="", graph_nodes=[], graph_edges=[])
    session.add(item)
    await session.flush()
    workspace = WorkspaceBuilder(session)
    item.source_uri = await workspace.store_upload(
        system, item.id, file.filename or f"document{suffix}", data, content
    )
    await workspace.sync_system(system.id)
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/{item_id}", response_model=KnowledgeOut)
async def get_knowledge(item_id: str, session: DbSession,
                        _: User = Depends(require_permission("inventory:read"))):
    return await _get(session, item_id)


@router.put("/{item_id}", response_model=KnowledgeOut)
async def update_knowledge(item_id: str, payload: KnowledgeWrite, session: DbSession,
                           _: User = Depends(require_permission("inventory:write"))):
    item = await _get(session, item_id)
    old_system_id = item.system_id
    workspace = WorkspaceBuilder(session)
    await workspace.remove_document_files(item)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    await session.flush()
    await workspace.sync_system(item.system_id)
    if old_system_id != item.system_id:
        await workspace.sync_system(old_system_id)
    await session.commit()
    await session.refresh(item)
    return item


@router.post("/{item_id}/reindex", response_model=KnowledgeOut)
async def reindex_knowledge(item_id: str, session: DbSession,
                            _: User = Depends(require_permission("inventory:write"))):
    item = await _get(session, item_id)
    if item.source_uri:
        workspace = WorkspaceBuilder(session)
        try:
            path = workspace.resolve_uri(item.source_uri)
        except ValueError:
            path = Path(item.source_uri)
            if path.parent.resolve() != LEGACY_STORAGE.resolve():
                raise HTTPException(status_code=404, detail="Knowledge source file is unavailable")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Knowledge source file is unavailable")
        generated = await asyncio.to_thread(extract_document, path.read_bytes(), path.suffix.lower())
        system = await session.get(System, item.system_id)
        if system:
            await workspace.storage.write_text(
                f"{workspace.workspace_relative(system)}/generated/{item.id}--reindexed.md", generated
            )
        if not item.source_uri.startswith("workspace://"):
            item.content_text = generated
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/{item_id}/download")
async def download_knowledge(item_id: str, session: DbSession,
                             _: User = Depends(require_permission("inventory:read"))):
    item = await _get(session, item_id)
    if item.source_uri:
        try:
            path = WorkspaceBuilder(session).resolve_uri(item.source_uri)
        except ValueError:
            path = Path(item.source_uri)
        allowed_legacy = path.parent.resolve() == LEGACY_STORAGE.resolve()
        if path.is_file() and (item.source_uri.startswith("workspace://") or allowed_legacy):
            return Response(await asyncio.to_thread(path.read_bytes), media_type="application/octet-stream",
                            headers={"Content-Disposition": f'attachment; filename="{path.name}"'})
    return Response(item.content_text, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{item.id}.txt"'})


@router.delete("/{item_id}", status_code=204)
async def delete_knowledge(item_id: str, session: DbSession,
                           _: User = Depends(require_permission("inventory:write"))):
    item = await _get(session, item_id)
    system_id = item.system_id
    workspace = WorkspaceBuilder(session)
    await workspace.remove_document_files(item)
    await session.delete(item)
    await session.flush()
    await workspace.sync_system(system_id)
    await session.commit()
    return Response(status_code=204)
