from dataclasses import dataclass
import re
import shlex
from typing import Any

from app.core.exceptions import AppError


@dataclass(frozen=True)
class CommandTemplate:
    linux: str | None = None
    windows: str | None = None
    docker: str | None = None
    kubernetes: str | None = None


@dataclass(frozen=True)
class ToolDescriptorInternal:
    name: str
    plugin: str
    description: str
    risk_level: str
    target_types: tuple[str, ...]
    arguments_schema: dict[str, Any]
    command_template: CommandTemplate
    output_limit_bytes: int | None = None


class ToolRegistry:
    _public_tool_names = ("run_ssh_command",)

    def __init__(self) -> None:
        self._tools: dict[str, ToolDescriptorInternal] = {}
        self._register_defaults()

    def all(self) -> list[ToolDescriptorInternal]:
        """Return only tools exposed to AI and the Policy Tools UI.

        Fixed discovery actions remain internally addressable through ``get`` so existing
        discovery plugins keep their stable command mappings without expanding the AI contract.
        """
        return [self._tools[name] for name in self._public_tool_names]

    def get(self, name: str) -> ToolDescriptorInternal:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise AppError(f"Unsupported tool action: {name}", 404) from exc

    def render_command(self, name: str, os_name: str, arguments: dict[str, Any]) -> str:
        tool = self.get(name)
        if name == "run_ssh_command":
            from app.services.command_guard import SshCommandGuard
            unexpected = set(arguments) - {"command"}
            if unexpected or not isinstance(arguments.get("command"), str):
                raise AppError("run_ssh_command requires only a string command", 422)
            return SshCommandGuard().validate(arguments["command"], os_name).command
        template = self._select_template(tool.command_template, os_name)
        if template is None:
            raise AppError(f"Action {name} is not supported for OS/target {os_name}", 400)
        safe_arguments = self._validate_arguments(tool, arguments, os_name)
        return template.format(**safe_arguments)

    def supports_target(self, tool: ToolDescriptorInternal, server_type: str, os_name: str) -> bool:
        normalized_os = "windows" if "win" in os_name.lower() else "linux"
        return server_type.lower() in tool.target_types or normalized_os in tool.target_types

    def _add(self, tool: ToolDescriptorInternal) -> None:
        self._tools[tool.name] = tool

    def _register_defaults(self) -> None:
        self._add(
            ToolDescriptorInternal(
                name="run_ssh_command",
                plugin="ssh.command_proposal",
                description=("Propose one read-only Linux diagnostic command for backend validation, "
                             "policy evaluation, approval, SSH execution and audit. When no target "
                             "is selected, server_id is supplied by the scoped runtime contract."),
                risk_level="low",
                target_types=("linux", "windows", "database", "docker", "kubernetes"),
                arguments_schema={"command": {"type": "string", "minLength": 1,
                                                "maxLength": 512}},
                command_template=CommandTemplate(),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="check_disk",
                plugin="ssh.linux_windows",
                description="Read-only disk utilization check",
                risk_level="low",
                target_types=("linux", "windows"),
                arguments_schema={},
                command_template=CommandTemplate(
                    linux="df -h", windows="Get-PSDrive -PSProvider FileSystem"
                ),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="check_cpu",
                plugin="ssh.linux_windows",
                description="Read-only CPU load check",
                risk_level="low",
                target_types=("linux", "windows"),
                arguments_schema={},
                command_template=CommandTemplate(
                    linux="top -bn1 | head -20",
                    windows="Get-Counter '\\Processor(_Total)\\% Processor Time'",
                ),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="check_memory",
                plugin="ssh.linux_windows",
                description="Read-only memory utilization check",
                risk_level="low",
                target_types=("linux", "windows"),
                arguments_schema={},
                command_template=CommandTemplate(
                    linux="free -m", windows="Get-CimInstance Win32_OperatingSystem"
                ),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="check_service",
                plugin="ssh.systemd_windows",
                description="Read-only service status check",
                risk_level="low",
                target_types=("linux", "windows"),
                arguments_schema={"service": {"type": "string", "pattern": "^[a-zA-Z0-9_.@-]+$"}},
                command_template=CommandTemplate(
                    linux="systemctl status {service} --no-pager",
                    windows="Get-Service -Name '{service}'",
                ),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="tail_log",
                plugin="ssh.logs",
                description="Read-only tail of an approved log path",
                risk_level="medium",
                target_types=("linux", "windows"),
                arguments_schema={
                    "path": {"type": "string"},
                    "lines": {"type": "integer", "minimum": 1, "maximum": 500},
                },
                command_template=CommandTemplate(
                    linux="tail -n {lines} {path}",
                    windows="Get-Content -Tail {lines} -Path {path}",
                ),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="journal_service_log", plugin="ssh.logs",
                description="Read recent journal entries for an approved service",
                risk_level="medium", target_types=("linux",),
                arguments_schema={
                    "service": {"type": "string", "pattern": "^[a-zA-Z0-9_.@-]+$"},
                    "lines": {"type": "integer", "minimum": 1, "maximum": 500},
                },
                command_template=CommandTemplate(
                    linux="journalctl -u {service} -n {lines} --no-pager"),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="restart_service",
                plugin="ssh.systemd_windows",
                description="Restart an approved service through least-privilege sudo policy",
                risk_level="high",
                target_types=("linux", "windows"),
                arguments_schema={"service": {"type": "string", "pattern": "^[a-zA-Z0-9_.@-]+$"}},
                command_template=CommandTemplate(
                    linux="sudo -n systemctl restart {service}",
                    windows="Restart-Service -Name '{service}'",
                ),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="docker_ps",
                plugin="docker",
                description="List Docker containers",
                risk_level="low",
                target_types=("docker", "linux"),
                arguments_schema={},
                command_template=CommandTemplate(
                    linux=("docker ps --format '{{{{.ID}}}}|{{{{.Image}}}}|{{{{.Names}}}}|"
                           "{{{{.Networks}}}}|{{{{.Ports}}}}|{{{{.Status}}}}'"),
                    docker="docker ps",
                ),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="kubectl_get_pods",
                plugin="kubernetes",
                description="List Kubernetes pods in namespace",
                risk_level="low",
                target_types=("kubernetes", "linux"),
                arguments_schema={"namespace": {"type": "string", "pattern": "^[a-zA-Z0-9_.-]+$"}},
                command_template=CommandTemplate(
                    linux="kubectl get pods -n {namespace}",
                    kubernetes="kubectl get pods -n {namespace}",
                ),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="system_information",
                plugin="ssh.linux_windows",
                description="Read operating system, uptime, hostname and execution identity",
                risk_level="low",
                target_types=("linux", "windows", "database", "docker", "kubernetes"),
                arguments_schema={},
                command_template=CommandTemplate(
                    linux="uname -a && cat /etc/os-release && uptime && hostname && whoami",
                    windows=("Get-ComputerInfo | Select-Object WindowsProductName,"
                             "WindowsVersion,OsArchitecture,CsName"),
                ),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="hardware_information",
                plugin="discovery.linux_windows",
                description="Read static CPU core, physical memory and disk capacity inventory",
                risk_level="low",
                target_types=("linux", "windows", "database", "docker", "kubernetes"),
                arguments_schema={},
                command_template=CommandTemplate(
                    linux="nproc && grep MemTotal /proc/meminfo && lsblk -bdno NAME,SIZE,TYPE",
                    windows=("Get-CimInstance Win32_ComputerSystem | Select-Object "
                             "NumberOfLogicalProcessors,TotalPhysicalMemory; "
                             "Get-CimInstance Win32_DiskDrive | Select-Object DeviceID,Size"),
                ),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="check_process",
                plugin="ssh.process",
                description="List the highest CPU processes",
                risk_level="low",
                target_types=("linux", "windows", "database", "docker"),
                arguments_schema={},
                command_template=CommandTemplate(
                    linux="ps aux --sort=-%cpu | head -25",
                    windows="Get-Process | Sort-Object CPU -Descending | Select-Object -First 20",
                ),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="check_network",
                plugin="ssh.network",
                description="Read interface addresses and listening connections",
                risk_level="low",
                target_types=("linux", "windows", "database", "docker", "kubernetes", "network"),
                arguments_schema={},
                command_template=CommandTemplate(
                    linux="ip addr && ss -tulpn",
                    windows=("Get-NetIPAddress | Format-Table; Get-NetTCPConnection | "
                             "Select-Object -First 30"),
                ),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="list_filesystems", plugin="discovery.linux_windows",
                description="List mounted filesystems and volumes", risk_level="low",
                target_types=("linux", "windows", "database", "docker", "kubernetes"),
                arguments_schema={}, command_template=CommandTemplate(
                    linux="findmnt -J -o TARGET,SOURCE,FSTYPE,SIZE,OPTIONS",
                    windows=("Get-Volume | Select-Object DriveLetter,FileSystemLabel,"
                             "FileSystem,Size,SizeRemaining")),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="list_services", plugin="discovery.services",
                description="List running services for evidence-based application discovery",
                risk_level="low", target_types=("linux", "windows", "database", "docker"),
                arguments_schema={}, command_template=CommandTemplate(
                    linux="systemctl list-units --type=service --state=running --no-pager --plain",
                    windows="Get-Service | Where-Object Status -eq 'Running'"),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="list_connections", plugin="discovery.network",
                description="List current TCP and UDP connections", risk_level="low",
                target_types=("linux", "windows", "database", "docker", "kubernetes", "network"),
                arguments_schema={}, command_template=CommandTemplate(
                    linux="ss -H -tunap", windows=("Get-NetTCPConnection | Select-Object "
                    "LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess")),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="list_deployed_applications", plugin="discovery.process",
                description="List process names and arguments for deployed application detection",
                risk_level="low", target_types=("linux", "windows", "database", "docker"),
                arguments_schema={}, command_template=CommandTemplate(
                    linux="ps -eo comm --no-headers",
                    windows="Get-Process | Select-Object ProcessName,Path"),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="docker_inventory", plugin="discovery.docker",
                description="List containers, Docker networks and Compose projects",
                risk_level="low", target_types=("linux", "docker"), arguments_schema={},
                command_template=CommandTemplate(linux=("docker ps --format '{{{{.ID}}}}|{{{{.Image}}}}|"
                    "{{{{.Names}}}}|{{{{.Networks}}}}|{{{{.Ports}}}}|{{{{.Status}}}}' && "
                    "docker network ls --format '{{{{json .}}}}' && docker compose ls --format json"),
                    docker="docker ps"),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="kubernetes_inventory", plugin="discovery.kubernetes",
                description="List Kubernetes workloads, services, ingresses and pods",
                risk_level="low", target_types=("linux", "kubernetes"), arguments_schema={},
                command_template=CommandTemplate(
                    linux="kubectl get deployments,services,ingresses,pods -A -o wide",
                    kubernetes="kubectl get deployments,services,ingresses,pods -A -o wide"),
            )
        )

    def _select_template(self, templates: CommandTemplate, os_name: str) -> str | None:
        normalized = os_name.lower()
        if "win" in normalized:
            return templates.windows
        if "kubernetes" in normalized:
            return templates.kubernetes or templates.linux
        if "docker" in normalized:
            return templates.docker or templates.linux
        return templates.linux

    def _validate_arguments(
        self, tool: ToolDescriptorInternal, arguments: dict[str, Any], os_name: str
    ) -> dict[str, Any]:
        required = set(tool.arguments_schema)
        missing = [key for key in required if key not in arguments]
        if missing:
            raise AppError(f"Missing required tool argument(s): {', '.join(missing)}", 422)
        unexpected = sorted(set(arguments) - required)
        if unexpected:
            raise AppError(f"Unexpected tool argument(s): {', '.join(unexpected)}", 422)
        safe = dict(arguments)
        if "lines" in arguments:
            if isinstance(arguments["lines"], bool):
                raise AppError("lines must be an integer", 422)
            try:
                lines = int(arguments["lines"])
            except (TypeError, ValueError) as exc:
                raise AppError("lines must be an integer", 422) from exc
            if lines < 1 or lines > 500:
                raise AppError("lines must be between 1 and 500", 422)
            safe["lines"] = lines
        for key in ("service", "namespace"):
            if key in arguments:
                value = str(arguments[key])
                if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", value):
                    raise AppError(f"Invalid {key}", 422)
                safe[key] = (
                    value.replace("'", "''") if "win" in os_name.lower() else shlex.quote(value)
                )
        if "path" in arguments:
            value = str(arguments["path"])
            windows = "win" in os_name.lower()
            pattern = (
                r"[A-Za-z]:\\[A-Za-z0-9_ .\\-]{1,480}" if windows else r"/[A-Za-z0-9_./-]{1,480}"
            )
            if not re.fullmatch(pattern, value) or ".." in value:
                raise AppError("Log path must be an absolute normalized path", 422)
            safe["path"] = (
                f"'{value.replace(chr(39), chr(39) * 2)}'" if windows else shlex.quote(value)
            )
        return safe
