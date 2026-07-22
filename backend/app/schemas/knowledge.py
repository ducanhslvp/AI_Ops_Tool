from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Timestamped


class KnowledgeWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_id: str
    title: str = Field(min_length=2, max_length=200)
    document_type: str = Field(pattern="^(pdf|docx|markdown|txt|runbook|architecture|diagram)$")
    content_text: str = Field(default="", max_length=2_000_000)
    graph_nodes: list[dict[str, Any]] = Field(default_factory=list, max_length=10_000)
    graph_edges: list[dict[str, Any]] = Field(default_factory=list, max_length=20_000)


class KnowledgeOut(Timestamped):
    system_id: str
    title: str
    document_type: str
    source_uri: str
    content_text: str
    graph_nodes: list[dict[str, Any]]
    graph_edges: list[dict[str, Any]]
