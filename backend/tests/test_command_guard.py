import pytest

from app.core.exceptions import AppError
from app.services.command_guard import SshCommandGuard
from app.services.ssh_gateway import SshGateway


@pytest.mark.parametrize("command", [
    "df -h",
    "systemctl status nginx --no-pager",
    "journalctl -u nginx -n 100 --no-pager",
    "docker ps",
    "kubectl get pods -n production",
])
def test_command_guard_accepts_bounded_read_only_commands(command: str) -> None:
    result = SshCommandGuard().validate(command, "Ubuntu 24.04")
    assert result.command


@pytest.mark.parametrize("command", [
    "rm -rf /",
    "df -h; shutdown now",
    "journalctl --file=/etc/shadow",
    "systemctl --root=/tmp status nginx",
    "docker inspect database",
    "kubectl get secrets -A",
    "cat /etc/passwd",
])
def test_command_guard_rejects_shell_and_secret_read_bypasses(command: str) -> None:
    with pytest.raises(AppError):
        SshCommandGuard().validate(command, "linux")


@pytest.mark.parametrize("command", [
    "Get-PSDrive -PSProvider FileSystem",
    "Get-CimInstance Win32_LogicalDisk",
    "Get-Service -Name nginx*",
    "Get-NetTCPConnection",
])
def test_command_guard_allows_read_only_windows_diagnostics(command: str) -> None:
    validated = SshCommandGuard().validate(command, "Windows Server 2022")
    assert validated.operation == "read"


@pytest.mark.parametrize("command", [
    "Restart-Service nginx",
    "Get-CimInstance Win32_UserAccount",
    "Get-Process | Stop-Process",
    "Get-PSDrive -PSProvider Registry",
])
def test_command_guard_rejects_unsafe_windows_commands(command: str) -> None:
    with pytest.raises(AppError):
        SshCommandGuard().validate(command, "Windows Server 2022")


def test_ssh_output_redacts_common_secret_shapes() -> None:
    value = "password=hunter2\nAuthorization: Bearer token-value\nstatus=healthy"
    safe = SshGateway._redact(value)
    assert "hunter2" not in safe
    assert "token-value" not in safe
    assert safe.count("[REDACTED]") == 2
