from dataclasses import dataclass
import base64
from pathlib import PurePosixPath
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
    _public_tool_names = (
        "run_ssh_command",
        "read_remote_file",
        "write_remote_file",
        "create_remote_directory",
        "move_remote_file",
        "delete_remote_file",
    )

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
        if name == "write_remote_file":
            return self._render_file_write(os_name, arguments)
        if name == "read_remote_file":
            return self._render_file_read(os_name, arguments)
        if name == "create_remote_directory":
            return self._render_directory_create(os_name, arguments)
        if name == "move_remote_file":
            return self._render_file_move(os_name, arguments)
        if name == "delete_remote_file":
            return self._render_file_delete(os_name, arguments)
        template = self._select_template(tool.command_template, os_name)
        if template is None:
            raise AppError(f"Action {name} is not supported for OS/target {os_name}", 400)
        safe_arguments = self._validate_arguments(tool, arguments, os_name)
        return template.format(**safe_arguments)

    def supports_target(self, tool: ToolDescriptorInternal, server_type: str, os_name: str) -> bool:
        normalized_os = "windows" if "win" in os_name.lower() else "linux"
        return server_type.lower() in tool.target_types or normalized_os in tool.target_types

    @staticmethod
    def _render_file_write(os_name: str, arguments: dict[str, Any]) -> str:
        from app.core.config import get_settings

        ToolRegistry._require_linux_file_target(os_name)
        if set(arguments) != {"path", "content", "mode"}:
            raise AppError("write_remote_file requires path, content and mode", 422)
        path = arguments["path"]
        content = arguments["content"]
        mode = arguments["mode"]
        if not isinstance(path, str) or not isinstance(content, str):
            raise AppError("Remote file path and content must be strings", 422)
        if mode not in {"replace", "append"}:
            raise AppError("Remote file mode must be replace or append", 422)
        settings = get_settings()
        encoded = content.encode("utf-8")
        if len(encoded) > settings.ssh_file_write_max_bytes:
            raise AppError("Remote file content exceeds the configured gateway limit", 422)
        normalized = ToolRegistry._validate_remote_path(
            path, settings.ssh_file_write_allowed_roots, "writable"
        )
        payload = base64.b64encode(encoded).decode("ascii")
        python_mode = "ab" if mode == "append" else "wb"
        script = (
            "import base64,pathlib,sys;"
            "p=pathlib.Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True);"
            f"p.open('{python_mode}').write(base64.b64decode(sys.argv[2]))"
        )
        return shlex.join(("python3", "-c", script, normalized, payload))

    @staticmethod
    def _render_file_read(os_name: str, arguments: dict[str, Any]) -> str:
        from app.core.config import get_settings

        ToolRegistry._require_linux_file_target(os_name)
        if set(arguments) - {"path", "max_bytes"} or "path" not in arguments:
            raise AppError("read_remote_file requires path and optional max_bytes", 422)
        settings = get_settings()
        path = ToolRegistry._validate_remote_path(
            arguments["path"], settings.ssh_file_read_allowed_roots, "readable"
        )
        max_bytes = arguments.get("max_bytes", settings.ssh_file_read_max_bytes)
        if not isinstance(max_bytes, int) or not 1 <= max_bytes <= settings.ssh_file_read_max_bytes:
            raise AppError("Remote file read size exceeds the configured gateway limit", 422)
        script = (
            "import pathlib,sys;"
            "p=pathlib.Path(sys.argv[1]);"
            "data=p.read_bytes();sys.stdout.buffer.write(data[:int(sys.argv[2])])"
        )
        return shlex.join(("python3", "-c", script, path, str(max_bytes)))

    @staticmethod
    def _render_directory_create(os_name: str, arguments: dict[str, Any]) -> str:
        from app.core.config import get_settings

        ToolRegistry._require_linux_file_target(os_name)
        if set(arguments) != {"path"}:
            raise AppError("create_remote_directory requires only path", 422)
        path = ToolRegistry._validate_remote_path(
            arguments["path"], get_settings().ssh_file_write_allowed_roots, "writable"
        )
        script = "import pathlib,sys;pathlib.Path(sys.argv[1]).mkdir(parents=True,exist_ok=True)"
        return shlex.join(("python3", "-c", script, path))

    @staticmethod
    def _render_file_move(os_name: str, arguments: dict[str, Any]) -> str:
        from app.core.config import get_settings

        ToolRegistry._require_linux_file_target(os_name)
        if set(arguments) != {"source_path", "destination_path", "overwrite"}:
            raise AppError(
                "move_remote_file requires source_path, destination_path and overwrite", 422
            )
        if not isinstance(arguments["overwrite"], bool):
            raise AppError("Remote file overwrite must be a boolean", 422)
        roots = get_settings().ssh_file_write_allowed_roots
        source = ToolRegistry._validate_remote_path(
            arguments["source_path"], roots, "writable"
        )
        destination = ToolRegistry._validate_remote_path(
            arguments["destination_path"], roots, "writable"
        )
        script = (
            "import pathlib,sys;"
            "src=pathlib.Path(sys.argv[1]);dst=pathlib.Path(sys.argv[2]);"
            "overwrite=sys.argv[3]=='1';"
            "dst.parent.mkdir(parents=True,exist_ok=True);"
            "(_ for _ in ()).throw(FileExistsError(str(dst))) "
            "if dst.exists() and not overwrite else src.replace(dst)"
        )
        return shlex.join(
            ("python3", "-c", script, source, destination,
             "1" if arguments["overwrite"] else "0")
        )

    @staticmethod
    def _render_file_delete(os_name: str, arguments: dict[str, Any]) -> str:
        from app.core.config import get_settings

        ToolRegistry._require_linux_file_target(os_name)
        if set(arguments) != {"path"}:
            raise AppError("delete_remote_file requires only path", 422)
        path = ToolRegistry._validate_remote_path(
            arguments["path"], get_settings().ssh_file_write_allowed_roots, "writable"
        )
        script = (
            "import pathlib,sys;"
            "p=pathlib.Path(sys.argv[1]);"
            "(_ for _ in ()).throw(IsADirectoryError(str(p))) if p.is_dir() else p.unlink()"
        )
        return shlex.join(("python3", "-c", script, path))

    @staticmethod
    def _require_linux_file_target(os_name: str) -> None:
        if "win" in os_name.casefold():
            raise AppError(
                "Structured remote file operations are not available for Windows", 422
            )

    @staticmethod
    def _validate_remote_path(path: object, roots: list[str], purpose: str) -> str:
        if not isinstance(path, str):
            raise AppError("Remote file path must be a string", 422)
        parsed = PurePosixPath(path)
        normalized = str(parsed)
        if not path.startswith("/") or ".." in parsed.parts:
            raise AppError("Remote file path must be absolute and cannot traverse parents", 403)
        forbidden_parts = {".ssh", ".gnupg", ".aws", ".azure", ".kube"}
        forbidden_names = {
            ".env", "id_rsa", "id_ed25519", "authorized_keys",
            "shadow", "gshadow", "sudoers",
        }
        lowered_parts = {part.casefold() for part in parsed.parts}
        if lowered_parts & forbidden_parts or parsed.name.casefold() in forbidden_names:
            raise AppError("Remote file path is protected by the Secret Isolation policy", 403)
        if not any(
            normalized == root or normalized.startswith(f"{root}/")
            for root in roots
        ):
            raise AppError(
                f"Remote file path is outside the configured {purpose} roots", 403
            )
        return normalized

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
                name="read_remote_file",
                plugin="ssh.file_operations",
                description=(
                    "Read a bounded text or configuration file through the SSH Gateway. "
                    "Protected secret locations are always denied."
                ),
                risk_level="medium",
                target_types=("linux", "database", "docker", "kubernetes"),
                arguments_schema={
                    "path": {"type": "string", "minLength": 2, "maxLength": 1024},
                    "max_bytes": {"type": "integer", "minimum": 1, "maximum": 2097152},
                },
                command_template=CommandTemplate(),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="write_remote_file",
                plugin="ssh.file_operations",
                description=(
                    "Create, replace or append a text file through the SSH Gateway. "
                    "Writable roots and content size are backend-controlled; Policy, "
                    "Permission, Approval and Audit remain enforced."
                ),
                risk_level="high",
                target_types=("linux", "database", "docker", "kubernetes"),
                arguments_schema={
                    "path": {"type": "string", "minLength": 2, "maxLength": 1024},
                    "content": {"type": "string"},
                    "mode": {"type": "string", "enum": ["replace", "append"]},
                },
                command_template=CommandTemplate(),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="create_remote_directory",
                plugin="ssh.file_operations",
                description="Create an approved directory inside a configured writable root.",
                risk_level="high",
                target_types=("linux", "database", "docker", "kubernetes"),
                arguments_schema={
                    "path": {"type": "string", "minLength": 2, "maxLength": 1024},
                },
                command_template=CommandTemplate(),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="move_remote_file",
                plugin="ssh.file_operations",
                description=(
                    "Move or rename one approved file without leaving configured writable roots."
                ),
                risk_level="high",
                target_types=("linux", "database", "docker", "kubernetes"),
                arguments_schema={
                    "source_path": {"type": "string", "minLength": 2, "maxLength": 1024},
                    "destination_path": {
                        "type": "string", "minLength": 2, "maxLength": 1024
                    },
                    "overwrite": {"type": "boolean"},
                },
                command_template=CommandTemplate(),
            )
        )
        self._add(
            ToolDescriptorInternal(
                name="delete_remote_file",
                plugin="ssh.file_operations",
                description=(
                    "Delete one approved file. Directory and recursive deletion are never allowed."
                ),
                risk_level="critical",
                target_types=("linux", "database", "docker", "kubernetes"),
                arguments_schema={
                    "path": {"type": "string", "minLength": 2, "maxLength": 1024},
                },
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
