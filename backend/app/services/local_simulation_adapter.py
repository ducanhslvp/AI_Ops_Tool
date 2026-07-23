import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.core.exceptions import AppError
from app.domain.models import Server
from app.services.tool_registry import ToolRegistry


@dataclass(frozen=True)
class SimulationResult:
    stdout: str
    stderr: str
    exit_status: int


class LocalSimulationAdapter:
    """Development-only command transport backed by reviewed output snapshots."""

    _COMMANDS: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"^df -(?:h|hP|hT|hPT|hTP)$"), "check_disk"),
        (re.compile(r"^Get-PSDrive -PSProvider FileSystem$"), "windows_disk"),
        (re.compile(r"^top -bn1 \| head -20$"), "check_cpu"),
        (re.compile(r"^Get-Counter '\\Processor\(_Total\)\\% Processor Time'$"), "windows_cpu"),
        (re.compile(r"^free -(?:h|m)$"), "check_memory"),
        (re.compile(r"^Get-CimInstance Win32_OperatingSystem$"), "windows_memory"),
        (re.compile(r"^systemctl status [A-Za-z0-9_.@-]+ --no-pager$"), "check_service"),
        (re.compile(r"^Get-Service -Name '[A-Za-z0-9_.@-]+'$"), "windows_service"),
        (re.compile(r"^tail -n [1-9][0-9]{0,2} /[A-Za-z0-9_./-]+$"), "tail_log"),
        (re.compile(r"^journalctl -u [A-Za-z0-9_.@-]+ -n [1-9][0-9]{0,2} --no-pager$"), "journal_log"),
        (re.compile(r"^Get-Content -Tail [1-9][0-9]{0,2} -Path '[A-Za-z]:\\[A-Za-z0-9_ .\\-]+'$"), "windows_log"),
        (re.compile(r"^sudo -n systemctl restart [A-Za-z0-9_.@-]+$"), "restart_service"),
        (re.compile(r"^Restart-Service -Name '[A-Za-z0-9_.@-]+'$"), "windows_restart"),
        (re.compile(r"^docker ps --format '\{\{\.ID\}\}\|\{\{\.Image\}\}\|\{\{\.Names\}\}\|\{\{\.Networks\}\}\|\{\{\.Ports\}\}\|\{\{\.Status\}\}'$"), "docker_ps"),
        (re.compile(r"^docker ps$"), "docker_ps"),
        (re.compile(r"^kubectl get pods -n [A-Za-z0-9_.-]+$"), "kubectl_pods"),
        (re.compile(r"^uname -a && cat /etc/os-release && uptime && hostname && whoami$"), "system_information"),
        (re.compile(r"^Get-ComputerInfo \| Select-Object WindowsProductName,WindowsVersion,OsArchitecture,CsName$"), "windows_system_information"),
        (re.compile(r"^nproc && grep MemTotal /proc/meminfo && lsblk -bdno NAME,SIZE,TYPE$"), "hardware_information"),
        (re.compile(r"^Get-CimInstance Win32_ComputerSystem \| Select-Object NumberOfLogicalProcessors,TotalPhysicalMemory; Get-CimInstance Win32_DiskDrive \| Select-Object DeviceID,Size$"), "windows_hardware_information"),
        (re.compile(r"^ps aux --sort=-%cpu \| head -25$"), "check_process"),
        (re.compile(r"^Get-Process \| Sort-Object CPU -Descending \| Select-Object -First 20$"), "windows_process"),
        (re.compile(r"^ip addr && ss -tulpn$"), "check_network"),
        (re.compile(r"^Get-NetIPAddress \| Format-Table; Get-NetTCPConnection \| Select-Object -First 30$"), "windows_network"),
        (re.compile(r"^findmnt -J -o TARGET,SOURCE,FSTYPE,SIZE,OPTIONS$"), "list_filesystems"),
        (re.compile(r"^Get-Volume \| Select-Object DriveLetter,FileSystemLabel,FileSystem,Size,SizeRemaining$"), "windows_filesystems"),
        (re.compile(r"^systemctl list-units --type=service --state=running --no-pager --plain$"), "list_services"),
        (re.compile(r"^Get-Service \| Where-Object Status -eq 'Running'$"), "windows_services"),
        (re.compile(r"^ss -H -tunap$"), "list_connections"),
        (re.compile(r"^Get-NetTCPConnection \| Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess$"), "windows_connections"),
        (re.compile(r"^ps -eo comm --no-headers$"), "list_applications"),
        (re.compile(r"^Get-Process \| Select-Object ProcessName,Path$"), "windows_applications"),
        (re.compile(r"^docker ps --format '\{\{\.ID\}\}\|\{\{\.Image\}\}\|\{\{\.Names\}\}\|\{\{\.Networks\}\}\|\{\{\.Ports\}\}\|\{\{\.Status\}\}' && docker network ls --format '\{\{json \.\}\}' && docker compose ls --format json$"), "docker_inventory"),
        (re.compile(r"^kubectl get deployments,services,ingresses,pods -A -o wide$"), "kubernetes_inventory"),
    )

    def __init__(self, settings: Settings) -> None:
        if not settings.test_features_enabled or settings.ssh_transport != "local_simulation":
            raise RuntimeError("Local simulation adapter is disabled")
        root = Path(settings.local_test_snapshot_path)
        if not root.is_absolute():
            root = Path(__file__).resolve().parents[2] / root
        self.root = root.resolve()
        manifest_path = self.root / "profiles.json"
        if not manifest_path.is_file():
            raise RuntimeError(f"Simulation profile manifest is missing: {manifest_path}")
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    def profiles(self) -> list[dict]:
        return [
            {"id": profile_id, **metadata}
            for profile_id, metadata in self.manifest["profiles"].items()
        ]

    async def execute(self, server: Server, command: str) -> SimulationResult:
        if command.startswith("python3 -c ") and any(marker in command for marker in (
            "base64.b64decode", "read_bytes", ".mkdir(", ".replace(", ".unlink("
        )):
            return SimulationResult(
                stdout="Development adapter simulated the validated remote file operation.",
                stderr="",
                exit_status=0,
            )
        profile = str((server.ssh_config or {}).get(
            "test_profile", self.manifest.get("active_profile", "healthy")
        ))
        key = self._snapshot_key(command, profile)
        profile_config = self.manifest["profiles"].get(profile)
        if profile_config is None:
            raise AppError("Development test profile is not registered", 422)
        override = profile_config.get("overrides", {}).get(key, key)
        path = self._safe_path(profile, override)
        if not path.is_file():
            path = self._safe_path("healthy", override)
        if not path.is_file():
            path = self._safe_path("healthy", key)
        if not path.is_file():
            raise AppError(f"No reviewed simulation snapshot exists for {key}", 501)
        output = await asyncio.to_thread(path.read_text, encoding="utf-8")
        exit_status = int(profile_config.get("exit_codes", {}).get(key, 0))
        if exit_status:
            return SimulationResult(stdout=output, stderr="", exit_status=exit_status)
        return SimulationResult(stdout=output, stderr="", exit_status=0)

    def _snapshot_key(self, command: str, profile: str) -> str:
        registry = ToolRegistry()
        for configured in self.manifest.get("commands", []):
            if configured["profile_id"] != profile:
                continue
            rendered = registry.render_command(
                configured["action"], configured["os_name"], configured.get("arguments", {})
            )
            if rendered == command:
                return str(configured["id"])
        for pattern, key in self._COMMANDS:
            if pattern.fullmatch(command):
                return key
        raise AppError("Command is not registered for local simulation", 403)

    def _safe_path(self, profile: str, key: str) -> Path:
        if not re.fullmatch(r"[a-z0-9_]+", profile) or not re.fullmatch(r"[a-z0-9_]+", key):
            raise AppError("Invalid simulation snapshot reference", 422)
        path = (self.root / profile / f"{key}.txt").resolve()
        if self.root not in path.parents:
            raise AppError("Simulation snapshot escaped configured root", 403)
        return path
