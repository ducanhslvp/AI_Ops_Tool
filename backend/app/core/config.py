from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AIOps Platform"
    app_env: Literal["development", "testing", "uat", "staging", "production"] = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./data/aiops.db"

    jwt_secret_key: str = Field(default="development-access-secret-change-me")
    jwt_refresh_secret_key: str = Field(default="development-refresh-secret-change-me")
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "aiops-platform"
    jwt_audience: str = "aiops-api"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    secret_encryption_key: str | None = None
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    rate_limit_per_minute: int = 120
    rate_limit_max_clients: int = 10_000
    trust_proxy_headers: bool = False

    ssh_connect_timeout_seconds: int = 10
    ssh_command_timeout_seconds: int = 30
    ssh_output_limit_bytes: int = 1024 * 1024
    ssh_max_attempts: int = 2
    ssh_known_hosts_file: str = "~/.ssh/known_hosts"
    ssh_transport: Literal["ssh", "local_simulation"] = "local_simulation"
    test_mode: bool = False
    local_test_snapshot_path: str = "tests/sample_outputs"
    auto_create_schema: bool = False
    metrics_enabled: bool = True
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "aiops-api"
    ai_provider_config_path: str = "config/providers.yaml"
    workspace_root: str = "data/workspaces"
    workspace_context_max_chars: int = Field(default=80_000, ge=8_000, le=500_000)
    workspace_recent_memory_files: int = Field(default=5, ge=1, le=25)
    ai_command_consent_timeout_seconds: int = Field(default=1800, ge=60, le=7200)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "Settings":
        if self.app_env in {"uat", "staging", "production"} and (
            self.test_mode or self.ssh_transport == "local_simulation"
        ):
            raise ValueError(
                "TEST_MODE and local_simulation transport are forbidden outside development/testing"
            )
        if self.app_env in {"staging", "production"}:
            insecure = {
                "JWT_SECRET_KEY": self.jwt_secret_key,
                "JWT_REFRESH_SECRET_KEY": self.jwt_refresh_secret_key,
                "SECRET_ENCRYPTION_KEY": self.secret_encryption_key or "",
            }
            for name, value in insecure.items():
                if len(value) < 32 or "change-me" in value or "development-" in value:
                    raise ValueError(f"{name} must be a unique secret of at least 32 characters")
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS is forbidden outside development")
        return self

    @property
    def test_features_enabled(self) -> bool:
        return self.app_env == "development" or (
            self.app_env == "testing" and self.test_mode
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
