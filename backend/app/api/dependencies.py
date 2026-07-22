from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import decode_token
from app.core.config import get_settings
from app.ai.gateway import AIGateway
from app.ai.runtime import get_ai_gateway
from app.db.session import get_db_session
from app.domain.models import Server, SshGatewayProfile, User
from app.services.secret_manager import LocalAesSecretManager, SecretManager
from app.services.local_simulation_adapter import LocalSimulationAdapter
from app.services.ssh_gateway import SshGateway
from app.services.tool_registry import ToolRegistry

bearer = HTTPBearer(auto_error=False)
tool_registry = ToolRegistry()
secret_manager = LocalAesSecretManager()


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_tool_registry() -> ToolRegistry:
    return tool_registry


def get_secret_manager() -> SecretManager:
    return secret_manager


async def get_ssh_gateway(
    session: DbSession,
    manager: Annotated[SecretManager, Depends(get_secret_manager)],
) -> SshGateway:
    settings = get_settings()
    profile = await session.scalar(select(SshGatewayProfile).where(
        SshGatewayProfile.is_active.is_(True)
    ).order_by(SshGatewayProfile.updated_at.desc()).limit(1))
    if profile:
        mapping = {
            "connect_timeout_seconds": "ssh_connect_timeout_seconds",
            "command_timeout_seconds": "ssh_command_timeout_seconds",
            "output_limit_bytes": "ssh_output_limit_bytes",
            "max_attempts": "ssh_max_attempts",
            "known_hosts_file": "ssh_known_hosts_file",
        }
        settings = settings.model_copy(update={
            target: profile.config[source]
            for source, target in mapping.items() if source in profile.config
        })
    adapter = (
        LocalSimulationAdapter(settings)
        if settings.test_features_enabled and settings.ssh_transport == "local_simulation"
        else None
    )
    return SshGateway(manager, adapter, settings)


def get_gateway() -> AIGateway:
    return get_ai_gateway()


async def get_current_user(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        payload = decode_token(credentials.credentials, "access")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc
    user = await session.get(User, str(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(permission: str):
    async def guard(user: CurrentUser) -> User:
        granted = {item.code for item in user.role.permissions}
        if permission not in granted and "*" not in granted:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return user

    return guard


async def get_server_or_404(session: DbSession, server_id: str) -> Server:
    server = await session.get(Server, server_id)
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    return server


def request_id_header(x_request_id: Annotated[str | None, Header()] = None) -> str | None:
    return x_request_id
