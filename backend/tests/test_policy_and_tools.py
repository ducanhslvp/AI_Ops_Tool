from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.domain.models.enums import PolicyDecision
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.services.tool_registry import ToolRegistry


def test_only_raw_ssh_command_is_exposed_to_ai() -> None:
    registry = ToolRegistry()
    assert [tool.name for tool in registry.all()] == ["run_ssh_command"]
    assert registry.get("check_disk").name == "check_disk"


def test_registry_blocks_unknown_shell_action() -> None:
    registry = ToolRegistry()
    with pytest.raises(Exception):
        registry.get("rm_rf")


def test_registry_renders_only_registered_action() -> None:
    registry = ToolRegistry()
    command = registry.render_command("check_service", "Ubuntu 24.04", {"service": "nginx"})
    assert command == "systemctl status nginx --no-pager"


@pytest.mark.asyncio
async def test_policy_defaults_high_risk_to_approval() -> None:
    class EmptyScalars:
        def all(self):
            return []

    class EmptyResult:
        def scalars(self):
            return EmptyScalars()

    class EmptySession:
        async def execute(self, _statement):
            return EmptyResult()

    registry = ToolRegistry()
    user = SimpleNamespace(role=SimpleNamespace(name="Operator"))
    server = SimpleNamespace(environment=SimpleNamespace(name="Production"), server_type="linux")
    engine = PolicyEngine(EmptySession())  # type: ignore[arg-type]
    context = PolicyContext(
        user=user,
        server=server,
        action="restart_service",
        tool=registry.get("restart_service"),
        requested_at=datetime.now(UTC),
    )

    assert await engine.evaluate(context) == PolicyDecision.approval_required


@pytest.mark.parametrize(
    "path",
    [
        "/var/log/app.log;id",
        "/var/log/$(id)",
        "/var/log/app.log\nwhoami",
        "../../etc/shadow",
        "/var/log/app.log > /tmp/out",
    ],
)
def test_registry_rejects_log_path_injection(path: str) -> None:
    registry = ToolRegistry()
    with pytest.raises(Exception):
        registry.render_command("tail_log", "Ubuntu", {"path": path, "lines": 10})
