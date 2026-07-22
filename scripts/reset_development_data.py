import asyncio

from development_seed import seed_development_data

from sqlalchemy import delete

from app.core.config import get_settings
from app.db.session import AsyncSessionFactory
from app.domain.models import (
    AiMessage, AiProviderConfiguration, AiSession, Alert, ApprovalRequest, AuditLog,
    Credential, DiscoveryScan, DiscoverySchedule, Environment, KnowledgeDocument,
    NotificationChannel, PlatformSetting,
    Plugin, PolicyRule, Report, ReportTemplate, Server, SshGatewayProfile, System,
)


async def reset() -> None:
    if not get_settings().test_features_enabled:
        raise RuntimeError("Development reset is disabled outside development/testing")
    ordered_models = [
        AiMessage, ApprovalRequest, AuditLog, DiscoveryScan, DiscoverySchedule,
        AiSession, Alert, Report, ReportTemplate,
        KnowledgeDocument, Server, Credential, System, Environment, PolicyRule, Plugin,
        PlatformSetting, NotificationChannel, SshGatewayProfile, AiProviderConfiguration,
    ]
    async with AsyncSessionFactory() as session:
        for model in ordered_models:
            await session.execute(delete(model))
        await session.commit()
    await seed_development_data()


if __name__ == "__main__":
    asyncio.run(reset())
