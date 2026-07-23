from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.domain.models.enums import PolicyDecision
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.services.tool_registry import ToolRegistry


def test_only_controlled_ssh_gateway_tools_are_exposed_to_ai() -> None:
    registry = ToolRegistry()
    assert [tool.name for tool in registry.all()] == [
        "run_ssh_command",
        "read_remote_file",
        "write_remote_file",
        "create_remote_directory",
        "move_remote_file",
        "delete_remote_file",
    ]
    assert registry.get("check_disk").name == "check_disk"


def test_registry_blocks_unknown_shell_action() -> None:
    registry = ToolRegistry()
    with pytest.raises(Exception):
        registry.get("rm_rf")


def test_registry_renders_only_registered_action() -> None:
    registry = ToolRegistry()
    command = registry.render_command("check_service", "Ubuntu 24.04", {"service": "nginx"})
    assert command == "systemctl status nginx --no-pager"


def test_registry_builds_structured_remote_file_write() -> None:
    command = ToolRegistry().render_command(
        "write_remote_file",
        "Ubuntu 24.04",
        {"path": "/opt/acme/app.conf", "content": "enabled=true\n", "mode": "replace"},
    )
    assert command.startswith("python3 -c ")
    assert "/opt/acme/app.conf" in command
    assert "enabled=true" not in command


@pytest.mark.parametrize(
    ("action", "arguments", "marker"),
    [
        ("read_remote_file", {"path": "/var/log/app.log", "max_bytes": 4096},
         "read_bytes"),
        ("create_remote_directory", {"path": "/opt/acme/releases"}, ".mkdir("),
        ("move_remote_file", {
            "source_path": "/opt/acme/app.conf",
            "destination_path": "/opt/acme/app.conf.bak",
            "overwrite": False,
        }, ".replace("),
        ("delete_remote_file", {"path": "/opt/acme/app.conf.bak"}, ".unlink("),
    ],
)
def test_registry_builds_structured_remote_file_operations(
    action: str, arguments: dict, marker: str
) -> None:
    command = ToolRegistry().render_command(action, "Ubuntu 24.04", arguments)
    assert command.startswith("python3 -c ")
    assert marker in command


@pytest.mark.parametrize(
    "path", ["/home/deploy/.ssh/id_rsa", "/home/app/.env", "/opt/../etc/shadow"]
)
def test_registry_protects_secret_paths(path: str) -> None:
    with pytest.raises(Exception):
        ToolRegistry().render_command(
            "read_remote_file", "Ubuntu", {"path": path, "max_bytes": 1024}
        )


@pytest.mark.parametrize("path", ["/etc/shadow", "/tmp/out", "/opt/../etc/passwd"])
def test_registry_rejects_remote_file_paths_outside_configured_roots(path: str) -> None:
    with pytest.raises(Exception):
        ToolRegistry().render_command(
            "write_remote_file",
            "Ubuntu",
            {"path": path, "content": "data", "mode": "replace"},
        )


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
