from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Timestamped


MemoryCategory = Literal["daily", "incidents", "operations", "summaries", "decisions"]


class AiMemoryOut(Timestamped):
    system_id: str
    session_id: str | None
    category: str
    topic: str
    summary: str
    details: dict
    source_type: str
    source_refs: list[str]
    file_path: str
    occurred_at: datetime
    archived_at: datetime | None


class AiSessionStatusOut(BaseModel):
    system_id: str
    provider: str
    status: str
    connected: bool
    last_activity: datetime | None
    workspace_path: str
    context_size: int
    memory_size: int
    active_conversations: int


class MemoryCompareRequest(BaseModel):
    left_id: str
    right_id: str


class MemoryCompareOut(BaseModel):
    left: AiMemoryOut
    right: AiMemoryOut
    diff: str


class MemoryMaintenanceRequest(BaseModel):
    confirm_system_code: str = Field(min_length=2, max_length=40)


class MemoryMaintenanceOut(BaseModel):
    operation: str
    system_id: str
    affected_records: int = 0
    detail: str


class MemoryExportOut(BaseModel):
    filename: str
    markdown: str
