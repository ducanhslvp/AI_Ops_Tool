from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import OrmModel


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    remember: bool = False


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: str = Field(min_length=20)


LogoutRequest = RefreshRequest


class SessionOut(OrmModel):
    id: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    user_agent: str | None
    ip_address: str | None


class PermissionOut(OrmModel):
    code: str
    description: str


class RoleOut(OrmModel):
    name: str
    description: str
    permissions: list[PermissionOut]


class UserOut(OrmModel):
    id: str
    email: EmailStr
    full_name: str
    is_active: bool
    role: RoleOut
    created_at: datetime
