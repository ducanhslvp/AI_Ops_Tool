import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AiSession, AuditLog, Server

_session_locks: dict[str, asyncio.Lock] = {}


def _lock(key: str) -> asyncio.Lock:
    return _session_locks.setdefault(key, asyncio.Lock())


class AiSessionManager:
    """Coordinates durable provider threads without coupling services to a provider implementation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @asynccontextmanager
    async def active(self, ai_session: AiSession, *, system_id: str,
                     workspace_path: str, context_size: int) -> AsyncIterator[None]:
        async with _lock(f"{system_id}:{ai_session.id}"):
            ai_session.system_id = system_id
            ai_session.status = "busy"
            ai_session.context_size = context_size
            ai_session.last_activity_at = datetime.now(UTC)
            memory = dict(ai_session.memory or {})
            memory["workspace_path"] = str(Path(workspace_path).resolve())
            ai_session.memory = memory
            await self.db.flush()
            try:
                yield
            except Exception:
                ai_session.status = "error"
                ai_session.last_activity_at = datetime.now(UTC)
                raise
            else:
                ai_session.status = "idle"
                ai_session.last_activity_at = datetime.now(UTC)

    @staticmethod
    def provider_metadata(ai_session: AiSession) -> dict[str, str]:
        return {"provider_session_id": ai_session.provider_session_id or ""}

    @staticmethod
    def accept_provider_session(ai_session: AiSession, provider_session_id: str | None) -> None:
        if provider_session_id:
            ai_session.provider_session_id = provider_session_id

    async def reconcile_system_ownership(self) -> int:
        rows = (await self.db.execute(
            select(AiSession, Server.system_id).join(
                AuditLog, AuditLog.session_id == AiSession.id
            ).join(Server, Server.id == AuditLog.server_id).where(AiSession.system_id.is_(None))
        )).all()
        updated = 0
        for ai_session, system_id in rows:
            if ai_session.system_id is None:
                ai_session.system_id = system_id
                updated += 1
        return updated
