from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("Password must not exceed 72 UTF-8 bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return False


def create_token(
    *,
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    secret = settings.jwt_refresh_secret_key if token_type == "refresh" else settings.jwt_secret_key
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": str(uuid4()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    if extra_claims:
        reserved = {"sub", "type", "iat", "exp", "jti", "iss", "aud"}
        if reserved.intersection(extra_claims):
            raise ValueError("Reserved JWT claims cannot be overridden")
        payload.update(extra_claims)
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, token_type: str = "access") -> dict[str, Any]:
    settings = get_settings()
    secret = settings.jwt_refresh_secret_key if token_type == "refresh" else settings.jwt_secret_key
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require_sub": True, "require_exp": True, "require_iat": True},
        )
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
    if payload.get("type") != token_type:
        raise ValueError("Invalid token type")
    if not payload.get("sub") or not payload.get("jti"):
        raise ValueError("Missing required token claims")
    return payload
