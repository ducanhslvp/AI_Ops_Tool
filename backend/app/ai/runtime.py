from functools import lru_cache
from pathlib import Path

from app.ai.gateway import AIGateway
from app.ai.manager import ProviderManager
from app.core.config import get_settings


@lru_cache
def get_provider_manager() -> ProviderManager:
    configured = Path(get_settings().ai_provider_config_path)
    if not configured.is_absolute():
        configured = Path(__file__).resolve().parents[2] / configured
    return ProviderManager(configured)


@lru_cache
def get_ai_gateway() -> AIGateway:
    return AIGateway(get_provider_manager())
