"""Idempotent SQLite bootstrap: migrate schema and reconcile required platform records."""

import asyncio
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import AsyncSessionFactory, engine  # noqa: E402
from app.domain.models import (  # noqa: E402
    AiProviderConfiguration, Environment, Permission, Role, SshGatewayProfile, System, User,
)

PERMISSIONS = (
    "*", "inventory:read", "inventory:write", "tool:execute", "ai:chat",
    "policy:read", "policy:write", "approval:decide", "audit:read", "audit:delete",
    "secret:read_metadata", "secret:write", "report:read", "report:write",
)


async def _one(session, model, column, value):
    return await session.scalar(select(model).where(column == value))


async def reconcile_core_data() -> None:
    settings = get_settings()
    password = os.getenv("AIOPS_BOOTSTRAP_ADMIN_PASSWORD")
    if not password:
        if settings.app_env in {"development", "testing"}:
            password = "Admin@123456"
        else:
            raise RuntimeError(
                "AIOPS_BOOTSTRAP_ADMIN_PASSWORD is required outside development/testing"
            )
    if len(password) < 12:
        raise RuntimeError("AIOPS_BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters")

    async with AsyncSessionFactory() as session:
        permissions: list[Permission] = []
        for code in PERMISSIONS:
            item = await _one(session, Permission, Permission.code, code)
            if item is None:
                item = Permission(code=code, description=f"Allows {code}")
                session.add(item)
            permissions.append(item)
        await session.flush()

        admin_role = await _one(session, Role, Role.name, "Admin")
        if admin_role is None:
            admin_role = Role(name="Admin", description="Platform administrator")
            session.add(admin_role)
        admin_role.permissions = permissions
        await session.flush()

        email = os.getenv("AIOPS_BOOTSTRAP_ADMIN_EMAIL", "admin@aiops.example.com").lower()
        admin = await _one(session, User, User.email, email)
        if admin is None:
            admin = User(
                email=email, full_name="AIOps Admin", password_hash=hash_password(password),
                role=admin_role, is_active=True,
            )
            session.add(admin)
        else:
            admin.role = admin_role
            admin.is_active = True

        for name, description, risk in (
            ("Development", "Development and controlled validation environment", 1),
            ("Production", "Production infrastructure", 10),
        ):
            if await _one(session, Environment, Environment.name, name) is None:
                session.add(Environment(name=name, description=description, risk_weight=risk))

        if await _one(session, System, System.code, "DEFAULT") is None:
            session.add(System(
                code="DEFAULT", name="Default System", owner="Platform Operations",
                criticality="medium", description="Initial System created by SQLite bootstrap.",
            ))

        if await _one(session, SshGatewayProfile, SshGatewayProfile.name, "default") is None:
            session.add(SshGatewayProfile(
                name="default", description="Default backend-controlled SSH Gateway limits",
                is_active=True, config={
                    "connect_timeout_seconds": settings.ssh_connect_timeout_seconds,
                    "command_timeout_seconds": settings.ssh_command_timeout_seconds,
                    "output_limit_bytes": settings.ssh_output_limit_bytes,
                    "max_attempts": settings.ssh_max_attempts,
                    "known_hosts_file": settings.ssh_known_hosts_file,
                },
            ))

        if await _one(
            session, AiProviderConfiguration, AiProviderConfiguration.name, "codex-cli-local"
        ) is None:
            session.add(AiProviderConfiguration(
                name="codex-cli-local", provider_type="codex", model="", enabled=True,
                is_active=False, exclusive_mode=True, config={
                    "mode": "cli", "executable": "codex", "timeout_seconds": 120,
                    "ephemeral": False, "verify_authentication": True,
                    "max_output_bytes": 2_000_000,
                },
            ))
        await session.commit()
    await engine.dispose()


def migrate() -> None:
    settings = get_settings()
    if not settings.database_url.startswith("sqlite"):
        raise RuntimeError("init_sqlite.py requires a sqlite DATABASE_URL")
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")


if __name__ == "__main__":
    migrate()
    asyncio.run(reconcile_core_data())
    print("SQLite schema and required platform data are ready.")
