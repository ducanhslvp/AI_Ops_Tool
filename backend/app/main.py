from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import select

from app.api.v1.router import api_router
from app.ai.runtime import get_provider_manager
from app.core.config import get_settings
from app.core.exceptions import install_exception_handlers
from app.core.logging import configure_logging
from app.core.telemetry import configure_telemetry
from app.db.base import Base
from app.db.session import engine
from app.db.session import AsyncSessionFactory
from app.domain.models import System
from app.middleware.rate_limit import InMemoryRateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.services.ai_provider_runtime import restore_persisted_provider
from app.services.ai_session_manager import AiSessionManager
from app.services.memory_service import MemoryService
from app.workspace import WorkspaceBuilder


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    provider_manager = get_provider_manager()
    if settings.auto_create_schema:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    await provider_manager.initialize()
    async with AsyncSessionFactory() as session:
        await restore_persisted_provider(session, provider_manager)
        await AiSessionManager(session).reconcile_system_ownership()
        workspace = WorkspaceBuilder(session)
        await workspace.sync_all()
        memory = MemoryService(session, workspace)
        for system in (await session.scalars(select(System))).all():
            await memory.reconcile_files(system)
        await session.commit()
    try:
        yield
    finally:
        await provider_manager.close()
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Enterprise AIOps Platform API Gateway",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        lifespan=lifespan,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        InMemoryRateLimitMiddleware,
        requests_per_minute=settings.rate_limit_per_minute,
        max_clients=settings.rate_limit_max_clients,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Total-Count", "X-Page", "X-Page-Size", "X-Request-ID"],
    )
    install_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    configure_telemetry(app, settings)
    return app


app = create_app()
