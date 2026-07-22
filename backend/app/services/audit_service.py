from datetime import UTC, datetime
from hashlib import sha256
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AuditLog


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        user_id: str | None,
        session_id: str | None,
        server_id: str | None,
        prompt: str | None,
        reasoning_summary: str | None,
        tool_name: str | None,
        ssh_command: str | None,
        output: str | None,
        decision: str | None,
        duration_ms: int,
        result: str,
        provider_input: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        request_id: str | None = None,
        context_sources: list[str] | None = None,
        tool_events: list[dict] | None = None,
        exit_code: int | None = None,
        approval_used: bool = False,
    ) -> AuditLog:
        previous = await self.session.scalar(
            select(AuditLog).order_by(AuditLog.sequence_number.desc()).limit(1)
        )
        previous_hash = previous.integrity_hash if previous else None
        sequence_number = previous.sequence_number + 1 if previous else 1
        now = datetime.now(UTC)
        material_values = [
                previous_hash or "GENESIS",
                now.isoformat(),
                user_id or "",
                session_id or "",
                server_id or "",
                prompt or "",
                reasoning_summary or "",
                tool_name or "",
                ssh_command or "",
                output or "",
                decision or "",
                str(duration_ms),
                result,
            ]
        material_values.extend([
            provider_input or "", provider or "", model or "", request_id or "",
            self._canonical_json(context_sources or []),
            self._canonical_json(tool_events or []), "2",
        ])
        material = "|".join(material_values)
        audit = AuditLog(
            sequence_number=sequence_number,
            created_at=now,
            user_id=user_id,
            session_id=session_id,
            server_id=server_id,
            prompt=prompt,
            provider_input=provider_input,
            provider=provider,
            model=model,
            request_id=request_id,
            context_sources=context_sources or [],
            tool_events=tool_events or [],
            reasoning_summary=reasoning_summary,
            tool_name=tool_name,
            ssh_command=ssh_command,
            output=output,
            decision=decision,
            duration_ms=duration_ms,
            exit_code=exit_code,
            approval_used=approval_used,
            result=result,
            integrity_hash=sha256(material.encode("utf-8")).hexdigest(),
            integrity_version=2,
        )
        self.session.add(audit)
        await self.session.flush()
        return audit

    async def verify_chain(self) -> tuple[bool, int]:
        result = await self.session.execute(
            select(AuditLog).order_by(AuditLog.sequence_number.asc())
        )
        previous_hash = "GENESIS"
        count = 0
        for item in result.scalars():
            material_values = [
                    previous_hash,
                    self._as_utc(item.created_at).isoformat(),
                    item.user_id or "",
                    item.session_id or "",
                    item.server_id or "",
                    item.prompt or "",
                    item.reasoning_summary or "",
                    item.tool_name or "",
                    item.ssh_command or "",
                    item.output or "",
                    item.decision or "",
                    str(item.duration_ms),
                    item.result,
                ]
            if item.integrity_version >= 2:
                material_values.extend([
                    item.provider_input or "", item.provider or "", item.model or "",
                    item.request_id or "", self._canonical_json(item.context_sources or []),
                    self._canonical_json(item.tool_events or []), str(item.integrity_version),
                ])
            material = "|".join(material_values)
            expected = sha256(material.encode("utf-8")).hexdigest()
            if expected != item.integrity_hash:
                return False, count
            previous_hash = item.integrity_hash
            count += 1
        return True, count

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _canonical_json(value: object) -> str:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                          default=str)
