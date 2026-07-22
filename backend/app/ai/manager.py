import asyncio
import logging
from pathlib import Path
from time import perf_counter

from app.ai.config import AIAdapterConfig, ProviderConfig, load_ai_config
from app.ai.errors import AIAdapterError, ProviderUnavailableError
from app.ai.metrics import AI_LATENCY, AI_REQUESTS, AI_RETRIES, AI_TOKENS
from app.ai.models import ChatRequest, ChatResponse, ProviderHealth
from app.ai.provider import AIProvider
from app.ai.providers import (
    ClaudeProvider, CodexProvider, GeminiProvider, LMStudioProvider, MockProvider, OllamaProvider,
    OpenAIProvider,
)

logger = logging.getLogger(__name__)


class ProviderManager:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self.config: AIAdapterConfig | None = None
        self._providers: dict[str, AIProvider] = {}
        self._active_name = ""
        self._exclusive = False
        self._lock = asyncio.Lock()

    @property
    def active_name(self) -> str:
        return self._active_name

    @property
    def active(self) -> AIProvider:
        try:
            return self._providers[self._active_name]
        except KeyError as exc:
            raise ProviderUnavailableError("No active AI provider") from exc

    @property
    def exclusive(self) -> bool:
        return self._exclusive

    @staticmethod
    def _build(config: ProviderConfig) -> AIProvider:
        factories = {
            "mock": lambda: MockProvider(config.model, int(config.extra.get("latency_ms", 5))),
            "openai": lambda: OpenAIProvider(config),
            "claude": lambda: ClaudeProvider(config),
            "gemini": lambda: GeminiProvider(config),
            "ollama": lambda: OllamaProvider(config),
            "lm_studio": lambda: LMStudioProvider(config),
            "codex": lambda: CodexProvider(config),
        }
        try:
            return factories[config.type]()
        except KeyError as exc:
            raise ValueError(f"Unsupported AI provider type: {config.type}") from exc

    async def initialize(self) -> None:
        await self.reload()

    async def reload(self) -> None:
        new_config = load_ai_config(self.config_path)
        if new_config.active_provider not in new_config.providers:
            raise ValueError("Active AI provider is not configured")
        async with self._lock:
            old = self._providers
            providers: dict[str, AIProvider] = {}
            for name, provider_config in new_config.providers.items():
                if not provider_config.enabled:
                    continue
                provider = self._build(provider_config)
                await provider.initialize()
                providers[name] = provider
            if new_config.active_provider not in providers:
                raise ValueError("Active AI provider is disabled")
            self.config = new_config
            self._providers = providers
            self._active_name = new_config.active_provider
            self._exclusive = False
        await asyncio.gather(*(provider.close() for provider in old.values()))
        logger.info("AI provider configuration loaded", extra={"provider": self._active_name})

    async def switch(self, name: str, *, exclusive: bool = False) -> None:
        async with self._lock:
            if name not in self._providers:
                raise ProviderUnavailableError(f"AI provider is not loaded: {name}")
            self._active_name = name
            self._exclusive = exclusive
        logger.info("Active AI provider switched", extra={"provider": name})

    async def load(self, name: str, config: ProviderConfig) -> None:
        provider = self._build(config)
        await provider.initialize()
        async with self._lock:
            previous = self._providers.get(name)
            self._providers[name] = provider
            if self.config is not None:
                self.config.providers[name] = config
        if previous is not None:
            await previous.close()
        logger.info("AI provider loaded", extra={"provider": name})

    async def test_connection(self, config: ProviderConfig) -> ProviderHealth:
        """Probe an isolated provider instance without changing the active runtime."""
        provider = self._build(config)
        try:
            await provider.initialize()
            return await provider.health_check()
        finally:
            await provider.close()

    async def unload(self, name: str) -> None:
        async with self._lock:
            if name == self._active_name:
                raise ProviderUnavailableError("Cannot unload the active AI provider")
            provider = self._providers.pop(name, None)
        if provider is not None:
            await provider.close()
        logger.info("AI provider unloaded", extra={"provider": name})

    async def reconnect(self, name: str) -> ProviderHealth:
        if self.config is None or name not in self.config.providers:
            raise ProviderUnavailableError(f"AI provider is not configured: {name}")
        await self.load(name, self.config.providers[name])
        return await self._providers[name].health_check()

    async def health(self) -> list[ProviderHealth]:
        results = await asyncio.gather(*(provider.health_check() for provider in self._providers.values()),
                                       return_exceptions=True)
        health: list[ProviderHealth] = []
        for name, result in zip(self._providers, results, strict=True):
            if isinstance(result, Exception):
                from app.ai.models import ProviderStatus
                health.append(ProviderHealth(provider=name, status=ProviderStatus.disconnected,
                                             detail=str(result)))
            else:
                health.append(result.model_copy(update={"provider": name}))
        return health

    def provider_info(self) -> list[dict]:
        return [{**provider.get_provider_info().model_dump(), "name": name,
                 "model_info": provider.get_model_info().model_dump(), "active": name == self._active_name}
                for name, provider in self._providers.items()]

    async def model_catalog(self) -> list[dict]:
        provider = self.active
        if hasattr(provider, "list_models"):
            return await provider.list_models()
        info = provider.get_model_info()
        return [{"id": info.model, "display_name": info.model, "description": "",
                 "is_default": True, "default_reasoning_effort": "medium",
                 "reasoning_efforts": ["low", "medium", "high"]}]

    async def chat(self, request: ChatRequest, progress=None) -> ChatResponse:
        if self.config is None:
            raise ProviderUnavailableError("Provider manager is not initialized")
        names = [self._active_name] if self._exclusive else [
            self._active_name, *self.config.fallback_providers
        ]
        last_error: Exception | None = None
        for name in dict.fromkeys(names):
            provider = self._providers.get(name)
            if provider is None:
                continue
            for attempt in range(self.config.retries + 1):
                started = perf_counter()
                try:
                    operation = (provider.chat_with_progress(request, progress)
                                 if progress and hasattr(provider, "chat_with_progress")
                                 else provider.chat(request))
                    response = await asyncio.wait_for(operation,
                                                      timeout=self.config.request_timeout_seconds)
                    AI_REQUESTS.labels(name, "success").inc()
                    AI_LATENCY.labels(name).observe(perf_counter() - started)
                    AI_TOKENS.labels(name, "input").inc(response.usage.input_tokens)
                    AI_TOKENS.labels(name, "output").inc(response.usage.output_tokens)
                    return response
                except (AIAdapterError, asyncio.TimeoutError) as exc:
                    last_error = exc
                    AI_REQUESTS.labels(name, "error").inc()
                    if attempt < self.config.retries and getattr(exc, "retryable", True):
                        AI_RETRIES.labels(name).inc()
                        await asyncio.sleep(self.config.retry_base_delay_seconds * (2**attempt))
                        continue
                    break
        if self._exclusive and last_error is not None:
            raise ProviderUnavailableError(
                f"Exclusive AI provider '{self._active_name}' failed: {last_error}"
            ) from last_error
        raise ProviderUnavailableError("All configured AI providers failed") from last_error

    async def cancel(self, request_id: str) -> bool:
        results = await asyncio.gather(*(p.cancel(request_id) for p in self._providers.values()))
        return any(results)

    async def close(self) -> None:
        await asyncio.gather(*(provider.close() for provider in self._providers.values()))
        self._providers.clear()
