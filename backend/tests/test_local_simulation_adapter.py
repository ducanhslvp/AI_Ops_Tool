from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import AppError
from app.domain.models import Server
from app.services.local_simulation_adapter import LocalSimulationAdapter
from app.services.tool_registry import ToolRegistry


SNAPSHOTS = Path(__file__).parent / "sample_outputs"


def _settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        app_env="development",
        ssh_transport="local_simulation",
        local_test_snapshot_path=str(SNAPSHOTS),
        **overrides,
    )


def _server(profile: str = "healthy", os_name: str = "Ubuntu 24.04") -> Server:
    return Server(
        system_id="system-id",
        environment_id="environment-id",
        hostname="local-test-01",
        ip_address="127.0.0.1",
        os=os_name,
        server_type="linux" if "win" not in os_name.lower() else "windows",
        role="test-target",
        description="Controlled local simulation target",
        tags=["development"],
        status="online",
        ssh_config={"test_profile": profile},
    )


@pytest.mark.asyncio
async def test_registered_tool_reads_realistic_profile_snapshot() -> None:
    adapter = LocalSimulationAdapter(_settings())
    command = ToolRegistry().render_command("check_disk", "Ubuntu 24.04", {})

    result = await adapter.execute(_server("disk_full"), command)

    assert result.exit_status == 0
    assert "Filesystem" in result.stdout
    assert "100%" in result.stdout
    assert len(result.stdout.splitlines()) >= 4


@pytest.mark.asyncio
async def test_read_only_df_format_variants_use_disk_snapshot() -> None:
    adapter = LocalSimulationAdapter(_settings())

    for command in ("df -h", "df -hP", "df -hT", "df -hPT", "df -hTP"):
        result = await adapter.execute(_server(), command)
        assert result.exit_status == 0
        assert "Filesystem" in result.stdout


@pytest.mark.asyncio
async def test_accepted_human_readable_memory_command_uses_snapshot() -> None:
    adapter = LocalSimulationAdapter(_settings())

    result = await adapter.execute(_server(), "free -h")

    assert result.exit_status == 0
    assert "Mem" in result.stdout


@pytest.mark.asyncio
async def test_adapter_rejects_arbitrary_shell_and_unknown_profile() -> None:
    adapter = LocalSimulationAdapter(_settings())
    with pytest.raises(AppError, match="not registered"):
        await adapter.execute(_server(), "whoami && Remove-Item C:\\data")
    with pytest.raises(AppError, match="profile is not registered"):
        await adapter.execute(_server("not_registered"), "df -h")


@pytest.mark.asyncio
async def test_windows_tool_uses_windows_snapshot() -> None:
    adapter = LocalSimulationAdapter(_settings())
    command = ToolRegistry().render_command("check_memory", "Windows Server 2022", {})
    result = await adapter.execute(_server(os_name="Windows Server 2022"), command)
    assert "Windows Server 2022 Datacenter" in result.stdout
    assert "FreePhysicalMemory" in result.stdout


def test_production_forbids_test_mode_and_simulation_transport() -> None:
    secure = {
        "jwt_secret_key": "a" * 40,
        "jwt_refresh_secret_key": "b" * 40,
        "secret_encryption_key": "c" * 40,
    }
    with pytest.raises(ValidationError, match="local_simulation"):
        Settings(_env_file=None, app_env="production", ssh_transport="local_simulation", **secure)
    with pytest.raises(ValidationError, match="TEST_MODE"):
        Settings(
            _env_file=None, app_env="production", ssh_transport="ssh", test_mode=True, **secure
        )


def test_production_accepts_only_real_ssh_transport() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        ssh_transport="ssh",
        jwt_secret_key="a" * 40,
        jwt_refresh_secret_key="b" * 40,
        secret_encryption_key="c" * 40,
    )
    assert not settings.test_features_enabled
