from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.config import ProviderConfig
from app.ai.manager import ProviderManager
from app.ai.models import ProviderHealth
from app.domain.models import AiProviderConfiguration


def provider_config_from_record(item: AiProviderConfiguration) -> ProviderConfig:
    """Translate persisted administration fields into the adapter configuration contract."""
    raw = dict(item.config or {})
    base = {
        "type": item.provider_type,
        "model": item.model or "",
        "mode": raw.pop("mode", None),
        "executable": raw.pop("executable", None),
        "timeout_seconds": raw.pop("timeout_seconds", 60),
        "enabled": item.enabled,
        "extra": raw,
    }
    return ProviderConfig.model_validate(base)


def apply_health(item: AiProviderConfiguration, health: ProviderHealth) -> None:
    item.health_status = health.status.value
    item.health_detail = health.detail
    item.detected_version = health.version
    item.last_health_check_at = datetime.now(timezone.utc)


async def restore_persisted_provider(session: AsyncSession, manager: ProviderManager) -> None:
    """Restore the DB-selected provider so process restarts preserve runtime behavior."""
    item = await session.scalar(
        select(AiProviderConfiguration).where(
            AiProviderConfiguration.is_active.is_(True),
            AiProviderConfiguration.enabled.is_(True),
        ).order_by(AiProviderConfiguration.updated_at.desc())
    )
    if item is None:
        item = AiProviderConfiguration(
            name="codex-cli-local", provider_type="codex", model="",
            config={"mode": "cli", "executable": "codex", "timeout_seconds": 120,
                    "ephemeral": False, "verify_authentication": True,
                    "max_output_bytes": 2_000_000},
            enabled=True, is_active=True, exclusive_mode=True,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
    config = provider_config_from_record(item)
    bootstrap_name = manager.active_name
    await manager.load(item.name, config)
    await manager.switch(item.name, exclusive=item.exclusive_mode)
    if bootstrap_name != item.name:
        await manager.unload(bootstrap_name)
