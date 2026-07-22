import asyncio
import difflib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AiMemory, AiMessage, AiSession, KnowledgeDocument, System
from app.services.document_extractor import extract_document
from app.workspace import WorkspaceBuilder


class MemoryService:
    """Owns searchable, secret-free memory metadata and its workspace projection."""

    def __init__(self, session: AsyncSession, workspace: WorkspaceBuilder | None = None) -> None:
        self.session = session
        self.workspace = workspace or WorkspaceBuilder(session)

    async def record(self, *, system_id: str, session_id: str, request: str, answer: str,
                     tool_events: list[dict], confidence: dict, provider: str,
                     context_sources: list[str] | tuple[str, ...]) -> list[AiMemory]:
        now = datetime.now(UTC)
        classifications: list[str] = []
        if tool_events:
            classifications.append("operation")
        if any(event.get("error") for event in tool_events):
            classifications.append("incident")
        if any(event.get("decision") for event in tool_events):
            classifications.append("decision")
        summary = answer.strip()[:4000] or "No final response was produced."
        topic = request.strip().replace("\n", " ")[:180] or "AI operation"
        payload = {
            "category": "summaries", "classifications": classifications,
            "request": request, "answer": summary, "context_sources": list(context_sources),
            "tool_events": tool_events, "confidence": confidence, "provider": provider,
            "result": "success",
        }
        file_path = await self.workspace.append_ai_memory(system_id, session_id, payload)
        if not file_path:
            return []
        record = AiMemory(
            system_id=system_id, session_id=session_id, category="summaries", topic=topic,
            summary=summary, details={"confidence": confidence, "tools": tool_events,
                                       "provider": provider,
                                       "classifications": classifications},
            source_type="conversation", source_refs=list(context_sources),
            file_path=file_path, occurred_at=now,
        )
        self.session.add(record)
        await self.session.flush()
        return [record]

    async def list(self, system_id: str, *, query: str | None, category: str | None,
                   archived: bool, offset: int, limit: int) -> tuple[list[AiMemory], int]:
        filters = [AiMemory.system_id == system_id]
        filters.append(AiMemory.archived_at.is_not(None) if archived else AiMemory.archived_at.is_(None))
        if category:
            filters.append(AiMemory.category == category)
        if query:
            term = f"%{query.strip()}%"
            filters.append(or_(AiMemory.topic.ilike(term), AiMemory.summary.ilike(term)))
        total = await self.session.scalar(select(func.count(AiMemory.id)).where(*filters)) or 0
        items = list((await self.session.scalars(
            select(AiMemory).where(*filters).order_by(AiMemory.occurred_at.desc())
            .offset(offset).limit(limit)
        )).all())
        return items, total

    async def reset_memory(self, system: System) -> int:
        count = await self.session.scalar(
            select(func.count(AiMemory.id)).where(AiMemory.system_id == system.id)
        ) or 0
        await self.session.execute(delete(AiMemory).where(AiMemory.system_id == system.id))
        conversations = list((await self.session.scalars(
            select(AiSession).where(AiSession.system_id == system.id)
        )).all())
        for conversation in conversations:
            conversation.provider_session_id = None
            conversation.memory = {"checked_tools": [], "workspace_reload_required": True}
        await self.workspace.clear_memory(system)
        await self.workspace.sync_system(system.id)
        return count

    async def reset_conversations(self, system: System) -> int:
        session_ids = list((await self.session.scalars(
            select(AiSession.id).where(AiSession.system_id == system.id)
        )).all())
        if session_ids:
            await self.session.execute(
                update(AiMemory).where(AiMemory.session_id.in_(session_ids)).values(session_id=None)
            )
            await self.session.execute(delete(AiMessage).where(AiMessage.session_id.in_(session_ids)))
            await self.session.execute(delete(AiSession).where(AiSession.id.in_(session_ids)))
        await self.workspace.clear_conversations(system)
        await self.workspace.sync_system(system.id)
        return len(session_ids)

    async def refresh_memory(self, system: System) -> int:
        await self.reset_memory(system)
        sessions = list((await self.session.scalars(
            select(AiSession).where(AiSession.system_id == system.id)
        )).all())
        rebuilt = 0
        for ai_session in sessions:
            messages = list((await self.session.scalars(
                select(AiMessage).where(AiMessage.session_id == ai_session.id)
                .order_by(AiMessage.created_at)
            )).all())
            for index in range(0, len(messages) - 1):
                if messages[index].role != "user" or messages[index + 1].role != "assistant":
                    continue
                assistant = messages[index + 1]
                safe_tools = [{"tool": event.get("tool"),
                               "decision": event.get("result", {}).get("decision"),
                               "error": event.get("result", {}).get("error")}
                              for event in assistant.tool_events]
                rebuilt += len(await self.record(
                    system_id=system.id, session_id=ai_session.id,
                    request=messages[index].content, answer=assistant.content,
                    tool_events=safe_tools, confidence=assistant.confidence,
                    provider=str((ai_session.memory or {}).get("provider", "unknown")),
                    context_sources=[],
                ))
        return rebuilt

    async def archive(self, system: System) -> int:
        now = datetime.now(UTC)
        records = list((await self.session.scalars(
            select(AiMemory).where(AiMemory.system_id == system.id,
                                   AiMemory.archived_at.is_(None))
        )).all())
        key = self.workspace.workspace_relative(system)
        for record in records:
            source = self.workspace.storage.resolve(record.file_path)
            if source.is_file() and not source.is_symlink():
                destination = f"{key}/memory/archive/{Path(record.file_path).name}"
                await self.workspace.storage.write_bytes(destination, source.read_bytes())
                await self.workspace.storage.remove(record.file_path)
                record.file_path = destination
            record.archived_at = now
        return len(records)

    async def refresh_knowledge(self, system: System) -> int:
        await self.workspace.clear_generated(system)
        await self.workspace.sync_system(system.id)
        documents = list((await self.session.scalars(
            select(KnowledgeDocument).where(KnowledgeDocument.system_id == system.id)
        )).all())
        regenerated = 0
        key = self.workspace.workspace_relative(system)
        for document in documents:
            if not document.source_uri.startswith("workspace://"):
                continue
            source = self.workspace.resolve_uri(document.source_uri)
            if not source.is_file() or source.is_symlink():
                continue
            data = await asyncio.to_thread(source.read_bytes)
            content = await asyncio.to_thread(extract_document, data, source.suffix.lower())
            await self.workspace.storage.write_text(
                f"{key}/generated/{document.id}--refreshed.md", content
            )
            regenerated += 1
        return regenerated

    async def reconcile_files(self, system: System) -> int:
        known = set((await self.session.scalars(
            select(AiMemory.file_path).where(AiMemory.system_id == system.id)
        )).all())
        key = self.workspace.workspace_relative(system)
        root = self.workspace.workspace_path(system)
        imported = 0
        for path in (root / "memory").glob("*/*.json"):
            relative = path.relative_to(self.workspace.storage.root).as_posix()
            if relative in known or "archive" in path.parts or path.is_symlink():
                continue
            try:
                payload = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
                occurred_at = datetime.fromisoformat(str(payload.get("timestamp")))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            session_id = str(payload.get("session_id") or "") or None
            if session_id and await self.session.get(AiSession, session_id) is None:
                session_id = None
            self.session.add(AiMemory(
                system_id=system.id, session_id=session_id, category=path.parent.name,
                topic=str(payload.get("request") or "Imported workspace memory")[:200],
                summary=str(payload.get("answer") or payload.get("result") or "Imported memory"),
                details={"provider": payload.get("provider", "unknown")},
                source_type="workspace_migration",
                source_refs=list(payload.get("context_sources") or []),
                file_path=f"{key}/memory/{path.parent.name}/{path.name}",
                occurred_at=occurred_at,
            ))
            imported += 1
        return imported

    async def size(self, system: System) -> int:
        root = self.workspace.workspace_path(system) / "memory"
        if not root.is_dir():
            return 0
        return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())

    @staticmethod
    def compare(left: AiMemory, right: AiMemory) -> str:
        return "\n".join(difflib.unified_diff(
            left.summary.splitlines(), right.summary.splitlines(),
            fromfile=left.topic, tofile=right.topic, lineterm="",
        ))
