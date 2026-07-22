import json
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    enabled: bool = True
    model: str = ""
    base_url: str | None = None
    api_key: SecretStr | None = None
    timeout_seconds: float = Field(default=60, gt=0, le=600)
    mode: str | None = None
    executable: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class AIAdapterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active_provider: str = "mock"
    fallback_providers: list[str] = Field(default_factory=list)
    retries: int = Field(default=2, ge=0, le=5)
    retry_base_delay_seconds: float = Field(default=0.25, ge=0, le=10)
    request_timeout_seconds: float = Field(default=90, gt=0, le=600)
    max_tool_rounds: int = Field(default=20, ge=1, le=100)
    providers: dict[str, ProviderConfig]


_ENV_PATTERN = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?::-(.*?))?\}")


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        return os.environ.get(name, default or "")

    return _ENV_PATTERN.sub(replace, value)


def load_ai_config(path: str | Path) -> AIAdapterConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise ValueError(f"AI provider configuration does not exist: {config_path}")
    raw_text = config_path.read_text(encoding="utf-8")
    if config_path.suffix.lower() == ".json":
        raw = json.loads(raw_text)
    elif config_path.suffix.lower() in {".yaml", ".yml"}:
        raw = yaml.safe_load(raw_text)
    else:
        raise ValueError("AI provider configuration must be JSON or YAML")
    if not isinstance(raw, dict):
        raise ValueError("AI provider configuration must be an object")
    expanded = _expand_env(raw)
    active_override = os.getenv("ACTIVE_PROVIDER")
    if active_override:
        expanded["active_provider"] = active_override
    return AIAdapterConfig.model_validate(expanded)
