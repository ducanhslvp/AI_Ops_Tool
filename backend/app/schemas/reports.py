from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Timestamped


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=200)
    system_id: str | None = None
    server_id: str | None = None
    format: Literal["markdown", "html", "pdf", "csv"] = "markdown"
    template_id: str | None = None


class ReportUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=200)


class ReportOut(Timestamped):
    system_id: str | None
    server_id: str | None
    title: str
    format: str
    content: str
    generated_by_user_id: str | None
