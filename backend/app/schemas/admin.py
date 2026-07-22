from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas.common import Timestamped


class NamedResource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=4000)


class RoleWrite(NamedResource):
    permission_ids: list[str] = Field(default_factory=list, max_length=200)


class RoleAdminOut(Timestamped):
    name: str
    description: str
    permission_ids: list[str]


class PermissionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9:*_.-]+$")
    description: str = Field(default="", max_length=255)


class PermissionAdminOut(Timestamped):
    code: str
    description: str


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=72)
    role_id: str
    is_active: bool = True


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    password: str | None = Field(default=None, min_length=12, max_length=72)
    role_id: str | None = None
    is_active: bool | None = None


class UserAdminOut(Timestamped):
    email: EmailStr
    full_name: str
    role_id: str
    role_name: str
    is_active: bool


class PluginWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=80)
    version: str = Field(default="1.0.0", min_length=1, max_length=40)
    enabled: bool = True
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    config_schema: dict[str, Any] = Field(default_factory=dict)


class PluginOut(Timestamped):
    name: str
    category: str
    version: str
    enabled: bool
    capabilities: list[str]
    config_schema: dict[str, Any]


class SettingWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field(default="platform", min_length=2, max_length=80)
    key: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9_.-]+$")
    value: dict[str, Any]
    description: str = Field(default="", max_length=255)


class SettingOut(Timestamped):
    scope: str
    key: str
    value: dict[str, Any]
    description: str


class NotificationWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    channel_type: Literal["email", "webhook", "slack", "teams", "in_app"]
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_endpoint(self) -> "NotificationWrite":
        if self.channel_type in {"webhook", "slack", "teams"} and not self.config.get("url"):
            raise ValueError("Webhook-based channels require config.url")
        return self


class NotificationOut(Timestamped):
    name: str
    channel_type: str
    config: dict[str, Any]
    enabled: bool


class SshGatewayWrite(NamedResource):
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_limits(self) -> "SshGatewayWrite":
        allowed = {"connect_timeout_seconds", "command_timeout_seconds", "output_limit_bytes",
                   "max_attempts", "known_hosts_file"}
        if set(self.config) - allowed:
            raise ValueError("SSH gateway config contains unsupported fields")
        ranges = {
            "connect_timeout_seconds": (1, 120),
            "command_timeout_seconds": (1, 900),
            "output_limit_bytes": (1024, 10 * 1024 * 1024),
            "max_attempts": (1, 5),
        }
        for key, (minimum, maximum) in ranges.items():
            value = self.config.get(key)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(f"{key} must be between {minimum} and {maximum}")
        return self


class SshGatewayOut(Timestamped):
    name: str
    description: str
    config: dict[str, Any]
    is_active: bool


class AiProviderWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9_-]+$")
    provider_type: Literal["codex", "openai", "claude", "gemini", "ollama", "lm_studio", "mock"]
    model: str = Field(default="", max_length=160)
    config: dict[str, Any] = Field(default_factory=dict)
    secret_reference: str | None = Field(default=None, max_length=160)
    enabled: bool = True
    is_active: bool = False
    exclusive_mode: bool = False

    @model_validator(mode="after")
    def forbid_inline_secrets(self) -> "AiProviderWrite":
        forbidden = {"api_key", "password", "token", "secret", "private_key"}
        if forbidden.intersection(key.lower() for key in self.config):
            raise ValueError("Provider secrets must use secret_reference")
        if self.provider_type != "codex" and not self.model.strip():
            raise ValueError("model is required for this provider")
        if self.provider_type == "codex":
            allowed = {
                "mode", "executable", "timeout_seconds", "profile", "codex_home",
                "ephemeral", "verify_authentication", "max_output_bytes",
            }
            if set(self.config) - allowed:
                raise ValueError("Codex CLI configuration contains unsupported fields")
            if self.secret_reference:
                raise ValueError("Codex CLI reuses local CLI authentication; no secret reference is allowed")
            if self.config.get("mode", "cli") != "cli":
                raise ValueError("Only the documented Codex CLI transport is supported")
        return self


class AiProviderConfigOut(Timestamped):
    name: str
    provider_type: str
    model: str
    config: dict[str, Any]
    secret_reference: str | None
    enabled: bool
    is_active: bool
    exclusive_mode: bool
    health_status: str
    health_detail: str | None
    detected_version: str | None
    last_health_check_at: datetime | None


class ReportTemplateWrite(NamedResource):
    format: Literal["markdown", "html", "pdf", "csv"] = "markdown"
    template_body: str = Field(min_length=5, max_length=100_000)
    is_active: bool = True


class ReportTemplateOut(Timestamped):
    name: str
    description: str
    format: str
    template_body: str
    is_active: bool
