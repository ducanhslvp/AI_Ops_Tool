import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.ai.config import AIAdapterConfig, ProviderConfig, load_ai_config
from app.ai.errors import ProviderUnavailableError, RequestCancelledError
from app.ai.gateway import AIGateway
from app.ai.manager import ProviderManager
from app.ai.models import AIMessage, ChatRequest, ProviderStatus, ToolCall, ToolDefinition
from app.ai.providers.codex import CodexProvider
from app.ai.providers.mock import MockProvider
from app.ai.providers.openai import OpenAIProvider


def request(message: str = "hello") -> ChatRequest:
    return ChatRequest(session_id="session-1", messages=(AIMessage(role="user", content=message),))


def test_codex_provider_rejects_executable_outside_allowlist(monkeypatch) -> None:
    monkeypatch.delenv("CODEX_EXECUTABLE_ALLOWLIST", raising=False)
    with pytest.raises(ValueError, match="ALLOWLIST"):
        CodexProvider(ProviderConfig(type="codex", model="test", executable="powershell.exe"))


def test_codex_provider_filters_child_environment(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "must-not-leak")
    monkeypatch.setenv("CODEX_HOME", "safe-home")
    environment = CodexProvider._isolated_environment()
    assert "DATABASE_URL" not in environment
    assert environment["CODEX_HOME"] == "safe-home"


def test_codex_provider_builds_persistent_resume_command(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_EXECUTABLE_ALLOWLIST", "codex;codex.exe")
    provider = CodexProvider(ProviderConfig(type="codex", executable="codex"))
    assert "--ephemeral" not in provider._base_exec_arguments()
    arguments = provider._resume_arguments("f65ba237-3670-46ee-a03f-77d734179c59")
    assert arguments[:2] == ["exec", "resume"]
    assert arguments[-1] == "f65ba237-3670-46ee-a03f-77d734179c59"


def test_codex_provider_prefers_standalone_windows_install(monkeypatch) -> None:
    local_app_data = Path("data/test-codex-local-app-data").resolve()
    executable = local_app_data / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.touch()
    try:
        monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
        assert CodexProvider._resolve_executable("codex") == str(executable)
    finally:
        executable.unlink(missing_ok=True)
        directory = executable.parent
        while directory != local_app_data.parent:
            directory.rmdir()
            directory = directory.parent


@pytest.mark.asyncio
async def test_mock_provider_lifecycle_health_and_chat() -> None:
    provider = MockProvider()
    assert (await provider.health_check()).status == ProviderStatus.disconnected
    await provider.initialize()
    assert (await provider.health_check()).status == ProviderStatus.ready
    response = await provider.chat(request())
    assert response.provider == "mock"
    assert response.confidence == pytest.approx(0.72)
    await provider.close()


@pytest.mark.asyncio
async def test_mock_stream_has_ordered_lifecycle_events() -> None:
    provider = MockProvider()
    await provider.initialize()
    events = [event async for event in provider.stream_chat(request())]
    assert events[0].type == "started"
    assert events[-1].type == "completed"
    assert "".join(event.delta or "" for event in events).strip()


@pytest.mark.asyncio
async def test_mock_tool_call_and_gateway_round_trip() -> None:
    provider = MockProvider()
    await provider.initialize()
    manager = ProviderManager("unused.yaml")
    manager.config = AIAdapterConfig(
        active_provider="mock", retries=0, providers={"mock": ProviderConfig(
            type="mock", model="mock-operations-v1")}
    )
    manager._providers = {"mock": provider}
    manager._active_name = "mock"
    gateway = AIGateway(manager)
    seen: list[ToolCall] = []
    progress_events: list[tuple[str, dict]] = []

    async def execute(call: ToolCall) -> dict:
        seen.append(call)
        return {"action": call.name, "decision": "allow", "stdout": "42% used"}

    async def progress(event_type: str, data: dict) -> None:
        progress_events.append((event_type, data))

    tool = ToolDefinition(name="check_disk", description="check disk",
                          parameters={"type": "object", "properties": {}})
    result = await gateway.chat(request("check disk" ).model_copy(update={"tools": (tool,)}),
                                tool_executor=execute, progress=progress)
    assert seen[0].name == "check_disk"
    assert result.tool_events[0]["result"]["stdout"] == "42% used"
    assert result.response.finish_reason == "stop"
    assert result.provider_inputs
    assert [event[0] for event in progress_events] == [
        "provider_started", "provider_completed", "tool_call", "tool_result",
        "provider_started", "provider_completed",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("/dev/sda2 20G 20G 0 100% /", "Disk utilization is critical"),
        ("redis-server.service Active: failed (Result: exit-code)", "Redis is unavailable"),
        ("TOTAL_LAG=18422", "Kafka consumer lag is high"),
        ("connect: Network is unreachable", "network-path failure"),
    ],
)
async def test_mock_provider_classifies_controlled_tool_evidence(
    output: str, expected: str
) -> None:
    provider = MockProvider(latency_ms=0)
    await provider.initialize()
    response = await provider.chat(
        ChatRequest(
            session_id="classification",
            messages=(
                AIMessage(role="user", content="Analyze the target"),
                AIMessage(role="tool", content=json.dumps({"stdout": output, "exit_code": 0})),
            ),
        )
    )
    assert expected in response.content
    assert response.confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_cancel_interrupts_inflight_mock_request() -> None:
    provider = MockProvider(latency_ms=100)
    await provider.initialize()
    chat_request = request()
    task = asyncio.create_task(provider.chat(chat_request))
    await asyncio.sleep(0.01)
    assert await provider.cancel(chat_request.request_id)
    with pytest.raises(RequestCancelledError):
        await task


class FailingProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    async def chat(self, chat_request: ChatRequest):
        self.attempts += 1
        raise ProviderUnavailableError("planned failure")


@pytest.mark.asyncio
async def test_manager_retries_then_falls_back() -> None:
    failing = FailingProvider()
    fallback = MockProvider(latency_ms=0)
    await failing.initialize()
    await fallback.initialize()
    manager = ProviderManager("unused.yaml")
    manager.config = AIAdapterConfig(
        active_provider="primary", fallback_providers=["fallback"], retries=2,
        retry_base_delay_seconds=0,
        providers={
            "primary": ProviderConfig(type="mock", model="mock"),
            "fallback": ProviderConfig(type="mock", model="mock"),
        },
    )
    manager._providers = {"primary": failing, "fallback": fallback}
    manager._active_name = "primary"
    response = await manager.chat(request())
    assert failing.attempts == 3
    assert response.provider == "mock"


@pytest.mark.asyncio
async def test_manager_timeout_falls_back() -> None:
    slow = MockProvider(latency_ms=100)
    fallback = MockProvider(latency_ms=0)
    await slow.initialize()
    await fallback.initialize()
    manager = ProviderManager("unused.yaml")
    manager.config = AIAdapterConfig(
        active_provider="slow", fallback_providers=["fallback"], retries=0,
        request_timeout_seconds=0.03,
        providers={"slow": ProviderConfig(type="mock", model="mock"),
                   "fallback": ProviderConfig(type="mock", model="mock")},
    )
    manager._providers = {"slow": slow, "fallback": fallback}
    manager._active_name = "slow"
    assert (await manager.chat(request())).provider == "mock"


@pytest.mark.asyncio
async def test_manager_exclusive_mode_never_uses_fallback() -> None:
    failing = FailingProvider()
    fallback = MockProvider(latency_ms=0)
    await failing.initialize()
    await fallback.initialize()
    manager = ProviderManager("unused.yaml")
    manager.config = AIAdapterConfig(
        active_provider="primary", fallback_providers=["fallback"], retries=0,
        providers={"primary": ProviderConfig(type="mock", model="mock"),
                   "fallback": ProviderConfig(type="mock", model="mock")},
    )
    manager._providers = {"primary": failing, "fallback": fallback}
    manager._active_name = "primary"
    manager._exclusive = True
    with pytest.raises(ProviderUnavailableError):
        await manager.chat(request())
    assert failing.attempts == 1


def test_codex_structured_response_maps_only_registered_tools() -> None:
    events = [{"item": {"type": "agent_message", "text": json.dumps({
        "answer": "Need disk evidence", "reasoning_summary": "Disk was not checked",
        "confidence": 0.6, "tool_calls": [
            {"name": "check_disk", "arguments_json": "{}"},
            {"name": "unregistered_command", "arguments_json": '{"command":"whoami"}'},
        ],
    })}}]
    payload = CodexProvider._payload(events)
    allowed = {"check_disk"}
    calls = [item for item in payload["tool_calls"] if item["name"] in allowed]
    assert calls == [{"name": "check_disk", "arguments_json": "{}"}]


def test_codex_provider_prompt_is_exact_auditable_input(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_EXECUTABLE_ALLOWLIST", "codex;codex.exe")
    provider = CodexProvider(ProviderConfig(type="codex", executable="codex"))
    chat_request = request("Explain ERP health")
    provider_input = provider._prompt(chat_request)
    assert "BACKEND TOOL REGISTRY:" in provider_input
    assert "user: Explain ERP health" in provider_input


def test_codex_resumed_tool_round_sends_only_tool_result(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_EXECUTABLE_ALLOWLIST", "codex;codex.exe")
    provider = CodexProvider(ProviderConfig(type="codex", executable="codex"))
    chat_request = ChatRequest(
        session_id="session-1",
        metadata={"provider_session_id": "thread-1"},
        messages=(
            AIMessage(role="system", content="large repeated workspace context"),
            AIMessage(role="user", content="check ERP disk"),
            AIMessage(role="assistant", content="Collecting evidence"),
            AIMessage(role="tool", name="run_ssh_command", content='{"stdout":"42%"}'),
        ),
    )
    provider_input = provider._prompt(chat_request)
    assert "BACKEND TOOL RESULT" in provider_input
    assert "42%" in provider_input
    assert "large repeated workspace context" not in provider_input
    assert "check ERP disk" not in provider_input


@pytest.mark.asyncio
async def test_manager_load_switch_health_reload_and_close() -> None:
    config_path = Path("data/test-ai-manager-providers.yaml")
    config_path.write_text(
        "active_provider: first\nproviders:\n  first:\n    type: mock\n    model: one\n"
        "  second:\n    type: mock\n    model: two\n",
        encoding="utf-8",
    )
    manager = ProviderManager(config_path)
    await manager.initialize()
    assert manager.active_name == "first"
    await manager.switch("second")
    assert manager.active.get_model_info().model == "two"
    assert all(item.status == ProviderStatus.ready for item in await manager.health())
    assert (await manager.reconnect("second")).status == ProviderStatus.ready
    config_path.write_text(
        "active_provider: second\nproviders:\n  second:\n    type: mock\n    model: reloaded\n",
        encoding="utf-8",
    )
    await manager.reload()
    assert manager.active.get_model_info().model == "reloaded"
    await manager.close()
    config_path.unlink(missing_ok=True)


def test_configuration_supports_json_yaml_and_environment(monkeypatch) -> None:
    monkeypatch.setenv("TEST_ACTIVE", "mock")
    yaml_path = Path("data/test-ai-providers.yaml")
    yaml_path.write_text(
        "active_provider: ${TEST_ACTIVE}\nproviders:\n  mock:\n    type: mock\n    model: safe\n",
        encoding="utf-8",
    )
    json_path = Path("data/test-ai-providers.json")
    json_path.write_text(json.dumps({"active_provider": "mock", "providers": {
        "mock": {"type": "mock", "model": "safe"}}}), encoding="utf-8")
    assert load_ai_config(yaml_path).active_provider == "mock"
    assert load_ai_config(json_path).providers["mock"].model == "safe"
    yaml_path.unlink(missing_ok=True)
    json_path.unlink(missing_ok=True)


def test_configuration_allows_one_hundred_controlled_tool_calls() -> None:
    config = AIAdapterConfig(
        active_provider="mock", max_tool_rounds=100,
        providers={"mock": ProviderConfig(type="mock", model="safe")},
    )
    assert config.max_tool_rounds == 100


@pytest.mark.asyncio
async def test_openai_responses_wire_mapping() -> None:
    provider = OpenAIProvider(ProviderConfig(type="openai", model="gpt-test", api_key="secret"))
    await provider.initialize()

    async def handler(request_: httpx.Request) -> httpx.Response:
        assert request_.headers["authorization"] == "Bearer secret"
        payload = json.loads(request_.content)
        assert payload["model"] == "gpt-test"
        return httpx.Response(200, json={
            "model": "gpt-test", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": "ready"}]}],
            "usage": {"input_tokens": 2, "output_tokens": 1},
        })

    await provider.client.aclose()
    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    response = await provider.chat(request())
    assert response.content == "ready"
    assert response.usage.input_tokens == 2
    await provider.close()


def test_secret_is_redacted_from_provider_config() -> None:
    config = ProviderConfig(type="openai", model="gpt-test", api_key="super-secret")
    assert "super-secret" not in repr(config)
