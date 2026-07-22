from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DiscoveryOptions(BaseModel):
    include_system_services: bool = False
    incremental: bool = True
    namespace: str = Field(default="default", pattern=r"^[A-Za-z0-9_.-]+$", max_length=128)


class DiscoveryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_id: str | None = None
    server_ids: list[str] = Field(default_factory=list, max_length=50)
    options: DiscoveryOptions = Field(default_factory=DiscoveryOptions)

    @model_validator(mode="after")
    def validate_scope(self) -> "DiscoveryCreate":
        if not self.system_id and not self.server_ids:
            raise ValueError("Select a system or at least one server")
        return self


class DiscoveryScanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    system_id: str | None
    baseline_scan_id: str | None
    scope_type: str
    server_ids: list[str]
    status: str
    options: dict[str, Any]
    summary: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    change_summary: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class DiscoveryScheduleWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=3, max_length=160)
    system_id: str | None = None
    server_ids: list[str] = Field(default_factory=list, max_length=50)
    interval_minutes: int = Field(default=1440, ge=15, le=525_600)
    incremental: bool = True
    include_system_services: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def validate_scope(self) -> "DiscoveryScheduleWrite":
        if not self.system_id and not self.server_ids:
            raise ValueError("Select a system or at least one server")
        return self


class DiscoveryScheduleOut(DiscoveryScheduleWrite):
    model_config = ConfigDict(from_attributes=True)
    id: str
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9_]+$", max_length=80)
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)


class SimulationCommandWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9_]+$", max_length=80)
    action: str = Field(pattern=r"^[a-z0-9_]+$", max_length=120)
    os_name: str = Field(min_length=2, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)
    profile_id: str = Field(pattern=r"^[a-z0-9_]+$", max_length=80)
    output: str = Field(max_length=1_048_576)
    exit_code: int = Field(default=0, ge=0, le=255)
