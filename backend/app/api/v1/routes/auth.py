from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select

from app.api.dependencies import CurrentUser, DbSession
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    SessionOut,
    TokenPair,
    UserOut,
)
from app.schemas.common import ApiMessage
from app.schemas.common import PaginationDep, set_pagination_headers
from app.domain.models import RefreshToken
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, request: Request, session: DbSession) -> TokenPair:
    service = AuthService(session)
    user = await service.authenticate(payload.email, payload.password)
    access, refresh, expires = await service.issue_tokens(
        user,
        remember=payload.remember,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    await session.commit()
    return TokenPair(access_token=access, refresh_token=refresh, expires_in=expires)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, session: DbSession) -> TokenPair:
    service = AuthService(session)
    _, access, refresh_token, expires = await service.refresh(payload.refresh_token)
    await session.commit()
    return TokenPair(access_token=access, refresh_token=refresh_token, expires_in=expires)


@router.post("/logout", response_model=ApiMessage)
async def logout(payload: LogoutRequest, user: CurrentUser, session: DbSession) -> ApiMessage:
    await AuthService(session).revoke(payload.refresh_token, user)
    await session.commit()
    return ApiMessage(message="Logged out")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/sessions", response_model=list[SessionOut])
async def sessions(user: CurrentUser, session: DbSession, response: Response,
                   pagination: PaginationDep) -> list[SessionOut]:
    total = await session.scalar(select(func.count(RefreshToken.id)).where(
        RefreshToken.user_id == user.id)) or 0
    set_pagination_headers(response, total, pagination)
    records = await AuthService(session).list_sessions(
        user, offset=pagination.offset, limit=pagination.page_size
    )
    return [SessionOut.model_validate(item) for item in records]


@router.delete("/sessions/{session_id}", response_model=ApiMessage)
async def revoke_session(session_id: str, user: CurrentUser, session: DbSession) -> ApiMessage:
    if not await AuthService(session).revoke_session(session_id, user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    await session.commit()
    return ApiMessage(message="Session revoked")
