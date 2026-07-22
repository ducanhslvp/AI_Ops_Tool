from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db_session
from app.domain.models import Permission, Role, User
from app.main import create_app


@pytest.mark.asyncio
async def test_login_me_and_refresh_rotation() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as seed_session:
        permission = Permission(code="inventory:read", description="Read inventory")
        role = Role(name="Viewer", description="Read only", permissions=[permission])
        seed_session.add(
            User(
                email="viewer@aiops.example.com",
                full_name="Viewer",
                password_hash=hash_password("Viewer@123456"),
                role=role,
            )
        )
        await seed_session.commit()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "viewer@aiops.example.com",
                "password": "Viewer@123456",
                "remember": False,
            },
        )
        assert login.status_code == 200
        first_tokens = login.json()

        me = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {first_tokens['access_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["role"]["name"] == "Viewer"

        rotated = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": first_tokens["refresh_token"]},
        )
        assert rotated.status_code == 200
        assert rotated.json()["refresh_token"] != first_tokens["refresh_token"]

        reuse = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": first_tokens["refresh_token"]},
        )
        assert reuse.status_code == 401

    await engine.dispose()
