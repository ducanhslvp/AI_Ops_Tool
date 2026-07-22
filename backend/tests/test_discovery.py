import json
from pathlib import Path
import shutil

import pytest
from fastapi import HTTPException

from app.api.v1.routes import development
from app.core.config import Settings
from app.domain.models import Server
from app.schemas.discovery import ProfileWrite, SimulationCommandWrite
from app.services.development_test_registry import DevelopmentTestRegistry
from app.services.local_simulation_adapter import LocalSimulationAdapter
from app.services.plugins.discovery import (
    DockerDiscoveryPlugin, HostDiscoveryPlugin, build_dependency_edges,
)
from app.services.tool_registry import ToolRegistry


def test_development_routes_are_hidden_outside_development(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None, app_env="testing", test_mode=True,
                        ssh_transport="local_simulation")
    monkeypatch.setattr(development, "get_settings", lambda: settings)

    with pytest.raises(HTTPException) as error:
        development.development_settings()

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_development_registry_adds_only_rendered_tool_actions() -> None:
    root = Path("data/test-discovery-registry")
    shutil.rmtree(root, ignore_errors=True)
    (root / "healthy").mkdir(parents=True)
    (root / "profiles.json").write_text(json.dumps({
        "active_profile": "healthy", "commands": [], "profiles": {
            "healthy": {"name": "Healthy", "description": "", "overrides": {},
                        "exit_codes": {}}
        },
    }), encoding="utf-8")
    tools = ToolRegistry()
    registry = DevelopmentTestRegistry(root, tools)
    await registry.upsert_profile(ProfileWrite(id="custom", name="Custom", description="Test"))
    await registry.upsert_command(SimulationCommandWrite(
        id="custom_disk", action="check_disk", os_name="Ubuntu 24.04", arguments={},
        profile_id="custom", output="Filesystem 100% /data", exit_code=0,
    ))
    await registry.activate("custom")
    settings = Settings(_env_file=None, app_env="development", test_mode=True,
                        ssh_transport="local_simulation", local_test_snapshot_path=str(root))
    adapter = LocalSimulationAdapter(settings)
    server = Server(system_id="system", environment_id="environment", hostname="host",
                    ip_address="127.0.0.1", os="Ubuntu 24.04", server_type="linux",
                    role="application", description="", tags=[], status="online", ssh_config={})
    result = await adapter.execute(server, tools.render_command("check_disk", server.os, {}))
    assert result.stdout == "Filesystem 100% /data"
    assert registry.commands("custom")[0]["command"] == "df -h"
    shutil.rmtree(root, ignore_errors=True)


def test_discovery_plugins_filter_system_services_and_parse_docker() -> None:
    node = {"id": "app", "data": {"role": "application", "system_id": "erp"}}
    evidence = {
        "hardware_information": "8\nMemTotal: 32768000 kB\nsda 536870912000 disk",
        "list_services": "nginx.service active running\nsystemd-journald.service active running",
        "docker_inventory": '{"Image":"erp:2","Names":"erp-api","Ports":"8080/tcp"}',
    }
    HostDiscoveryPlugin().enrich(node, evidence, False)
    DockerDiscoveryPlugin().enrich(node, evidence, False)
    assert node["data"]["cpu_cores"] == 8
    assert node["data"]["ram_bytes"] == 32768000 * 1024
    assert node["data"]["disk_total_bytes"] == 536870912000
    assert "nginx" in node["data"]["services"]
    assert "systemd-journald" not in node["data"]["services"]
    assert node["data"]["open_ports"] == node["data"]["listening_ports"]
    assert node["data"]["containers"][0]["name"] == "erp-api"


def test_dependency_inference_has_confidence_and_reason() -> None:
    nodes = [
        {"id": "app", "data": {"ip": "10.0.0.1", "role": "application",
                                  "system_id": "erp"}},
        {"id": "redis", "data": {"ip": "10.0.0.2", "role": "redis",
                                    "system_id": "erp"}},
    ]
    evidence = {"app": {"list_connections": (
        'tcp ESTAB 0 0 10.0.0.1:45000 10.0.0.2:6379 users:(("erp",pid=1))'
    )}}
    edges = build_dependency_edges(nodes, evidence)
    assert len(edges) == 1
    assert edges[0]["service_name"] == "redis"
    assert edges[0]["confidence"] > 0.9
    assert edges[0]["reason"]


def test_windows_hardware_capacity_table_is_parsed() -> None:
    node = {"id": "win", "data": {"role": "application", "system_id": "erp"}}
    evidence = {"hardware_information": (
        "NumberOfLogicalProcessors TotalPhysicalMemory\n"
        "------------------------- -------------------\n"
        "8                         34359738368\n\n"
        "DeviceID Size\n\\\\.\\PHYSICALDRIVE0 536870912000"
    )}

    HostDiscoveryPlugin().enrich(node, evidence, False)

    assert node["data"]["cpu_cores"] == 8
    assert node["data"]["ram_bytes"] == 34359738368
    assert node["data"]["disk_count"] == 1
