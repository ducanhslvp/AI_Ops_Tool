from datetime import UTC, datetime, timedelta
from hashlib import sha256

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import create_token, decode_token, verify_password
from app.domain.models import RefreshToken, User
from app.repositories.users import UserRepository


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.settings = get_settings()

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise AppError("Invalid email or password", status.HTTP_401_UNAUTHORIZED)
        if not user.is_active:
            raise AppError("User is disabled", status.HTTP_403_FORBIDDEN)
        return user

    async def issue_tokens(
        self,
        user: User,
        *,
        remember: bool,
        user_agent: str | None,
        ip_address: str | None,
    ) -> tuple[str, str, int]:
        access_minutes = self.settings.access_token_expire_minutes
        refresh_days = 30 if remember else self.settings.refresh_token_expire_days
        permission_codes = [permission.code for permission in user.role.permissions]
        access_token = create_token(
            subject=user.id,
            token_type="access",
            expires_delta=timedelta(minutes=access_minutes),
            extra_claims={"role": user.role.name, "permissions": permission_codes},
        )
        refresh_token = create_token(
            subject=user.id,
            token_type="refresh",
            expires_delta=timedelta(days=refresh_days),
        )
        self.session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=sha256(refresh_token.encode("utf-8")).hexdigest(),
                expires_at=datetime.now(UTC) + timedelta(days=refresh_days),
                user_agent=user_agent,
                ip_address=ip_address,
            )
        )
        await self.session.flush()
        return access_token, refresh_token, access_minutes * 60

    async def refresh(self, token: str) -> tuple[User, str, str, int]:
        try:
            payload = decode_token(token, "refresh")
        except ValueError as exc:
            raise AppError("Invalid refresh token", status.HTTP_401_UNAUTHORIZED) from exc
        token_hash = sha256(token.encode("utf-8")).hexdigest()
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        stored = result.scalar_one_or_none()
        now = datetime.now(UTC)
        if (
            stored is None
            or stored.revoked_at is not None
            or self._as_utc(stored.expires_at) <= now
        ):
            raise AppError("Invalid refresh token", status.HTTP_401_UNAUTHORIZED)
        user = await self.users.get(str(payload["sub"]))
        if user is None or not user.is_active or stored.user_id != user.id:
            raise AppError("Invalid refresh token", status.HTTP_401_UNAUTHORIZED)
        stored.revoked_at = now
        tokens = await self.issue_tokens(
            user,
            remember=False,
            user_agent=stored.user_agent,
            ip_address=stored.ip_address,
        )
        return (user, *tokens)

    async def revoke(self, token: str, user: User) -> None:
        token_hash = sha256(token.encode("utf-8")).hexdigest()
        result = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.user_id == user.id,
            )
        )
        stored = result.scalar_one_or_none()
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = datetime.now(UTC)
            await self.session.flush()

    async def list_sessions(self, user: User, *, offset: int = 0,
                            limit: int = 50) -> list[RefreshToken]:
        result = await self.session.execute(
            select(RefreshToken)
            .where(RefreshToken.user_id == user.id)
            .order_by(RefreshToken.created_at.desc())
                .offset(offset)
                .limit(limit)
        )
        return list(result.scalars())

    async def revoke_session(self, session_id: str, user: User) -> bool:
        stored = await self.session.get(RefreshToken, session_id)
        if stored is None or stored.user_id != user.id:
            return False
        if stored.revoked_at is None:
            stored.revoked_at = datetime.now(UTC)
            await self.session.flush()
        return True

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
