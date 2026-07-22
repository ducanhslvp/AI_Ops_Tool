from ipaddress import ip_address
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import Timestamped


class EnvironmentOut(Timestamped):
    name: str
    description: str
    risk_weight: int


class EnvironmentWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=255)
    risk_weight: int = Field(default=1, ge=1, le=10)


class SystemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    owner: str = ""
    description: str = ""
    criticality: str = "medium"


class SystemOut(Timestamped):
    name: str
    code: str
    owner: str
    description: str
    criticality: str


class ServerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_id: str
    environment_id: str
    credential_id: str | None = None
    hostname: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9.-]+$")
    ip_address: str
    os: str = Field(min_length=1, max_length=80)
    server_type: str = Field(pattern="^(linux|windows|database|docker|kubernetes|network)$")
    role: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    ssh_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ip_address")
    @classmethod
    def valid_ip(cls, value: str) -> str:
        return str(ip_address(value))

    @field_validator("ssh_config")
    @classmethod
    def valid_ssh_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        allowed = {"port", "known_hosts"}
        if set(value) - allowed:
            raise ValueError("ssh_config contains unsupported fields")
        port = value.get("port", 22)
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("SSH port must be between 1 and 65535")
        known_hosts = value.get("known_hosts")
        if known_hosts is not None and (
            not isinstance(known_hosts, str) or not known_hosts.strip()
        ):
            raise ValueError("known_hosts must be a non-empty path or pinned key")
        return value

class ServerOut(Timestamped):
    system_id: str
    environment_id: str
    credential_id: str | None
    credential_username: str = ""
    credential_scope: str = "none"
    hostname: str
    ip_address: str
    os: str
    server_type: str
    role: str
    description: str
    tags: list[str]
    status: str
    ssh_config: dict


class CredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    system_id: str
    secret_payload: dict[str, str]
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_secret_payload(self) -> "CredentialCreate":
        allowed = {"username", "password", "private_key", "certificate", "token"}
        if set(self.secret_payload) - allowed:
            raise ValueError("secret_payload contains unsupported fields")
        if not self.secret_payload.get("username"):
            raise ValueError("SSH credential requires username")
        if not any(self.secret_payload.get(key) for key in ("password", "private_key", "token")):
            raise ValueError("Credential requires password, private_key, or token")
        return self


class CredentialOut(Timestamped):
    name: str
    system_id: str | None
    username: str
    provider: str
    metadata_json: dict
    is_active: bool


class CredentialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    system_id: str
    username: str = Field(min_length=1, max_length=120)
    secret_payload: dict[str, str] | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_optional_secret(self) -> "CredentialUpdate":
        if self.secret_payload is not None:
            self.secret_payload["username"] = self.username
            CredentialCreate(name=self.name, secret_payload=self.secret_payload,
                             metadata_json=self.metadata_json, system_id=self.system_id)
        return self
