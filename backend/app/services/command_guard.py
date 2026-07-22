import re
import shlex
from dataclasses import dataclass

from app.core.exceptions import AppError


@dataclass(frozen=True)
class ValidatedCommand:
    command: str
    executable: str
    operation: str


class SshCommandGuard:
    """Parses a narrow read-only command language before dispatch to the SSH transport."""

    _forbidden = re.compile(r"[;&|><`\r\n]|\$\(|\$\{")
    _simple = {"df", "free", "uptime", "uname", "hostname", "hostnamectl", "top", "ps", "ss"}
    _subcommands = {
        "systemctl": {"status", "is-active", "is-enabled", "list-units", "show"},
        "journalctl": set(),
        "docker": {"ps", "stats", "version", "info", "network", "compose"},
        "kubectl": {"get", "describe", "logs", "top", "version", "cluster-info"},
        "ip": {"addr", "address", "link", "route", "neigh"},
    }
    _dangerous_words = re.compile(
        r"\b(rm|rmdir|shutdown|reboot|halt|poweroff|mkfs|fdisk|parted|dd|passwd|useradd|"
        r"userdel|chmod|chown|sudo|su|kill|pkill|iptables|nft|mount|umount)\b", re.I
    )
    _windows_commands = {
        "get-psdrive", "get-computerinfo", "get-process", "get-service",
        "get-netipaddress", "get-nettcpconnection", "get-ciminstance",
    }
    _windows_cim_classes = {
        "win32_logicaldisk", "win32_operatingsystem", "win32_computersystem",
        "win32_processor", "win32_service",
    }

    def validate(self, command: str, os_name: str) -> ValidatedCommand:
        value = command.strip()
        if not value or len(value) > 512:
            raise AppError("SSH command must contain between 1 and 512 characters", 422)
        if self._forbidden.search(value) or self._dangerous_words.search(value):
            raise AppError("SSH command contains a forbidden operator or executable", 403)
        try:
            tokens = shlex.split(value, posix=True)
        except ValueError as exc:
            raise AppError("SSH command has invalid quoting", 422) from exc
        if not tokens or len(tokens) > 40:
            raise AppError("SSH command contains too many arguments", 422)
        if any(".." in token for token in tokens):
            raise AppError("Parent path traversal is forbidden in SSH commands", 403)
        if "win" in os_name.casefold():
            return self._validate_windows(tokens)
        executable = tokens[0].casefold()
        operation = "read"
        if executable in self._simple:
            pass
        elif executable in self._subcommands:
            subcommand = next((token.casefold() for token in tokens[1:] if not token.startswith("-")), "")
            allowed = self._subcommands[executable]
            if allowed and subcommand not in allowed:
                raise AppError(f"Unsupported read-only {executable} operation", 403)
            operation = subcommand or "read"
            self._validate_nested(executable, tokens)
        else:
            raise AppError(f"Executable is not in the read-only SSH command allowlist: {executable}", 403)
        return ValidatedCommand(command=shlex.join(tokens), executable=executable,
                                operation=operation)

    def _validate_windows(self, tokens: list[str]) -> ValidatedCommand:
        executable = tokens[0].casefold()
        if executable not in self._windows_commands:
            raise AppError(
                f"PowerShell command is not in the read-only SSH allowlist: {executable}", 403
            )
        arguments = [token.casefold() for token in tokens[1:]]
        if executable == "get-psdrive" and arguments not in (
            [], ["-psprovider", "filesystem"],
        ):
            raise AppError("Get-PSDrive supports only the FileSystem provider", 403)
        if executable == "get-ciminstance" and (
            len(arguments) != 1 or arguments[0] not in self._windows_cim_classes
        ):
            raise AppError("Get-CimInstance class is not in the read-only allowlist", 403)
        if executable == "get-service" and arguments:
            if len(arguments) != 2 or arguments[0] != "-name" or not re.fullmatch(
                r"[a-z0-9_.@*-]+", arguments[1]
            ):
                raise AppError("Get-Service supports only a safe -Name filter", 403)
        if executable not in {"get-psdrive", "get-ciminstance", "get-service"} and arguments:
            raise AppError(f"{tokens[0]} does not accept arguments through this gateway", 403)
        return ValidatedCommand(command=" ".join(tokens), executable=executable,
                                operation="read")

    @staticmethod
    def _validate_nested(executable: str, tokens: list[str]) -> None:
        lowered = [token.casefold() for token in tokens]
        if executable == "docker":
            if "network" in lowered and not any(item in lowered for item in ("ls", "inspect")):
                raise AppError("Only docker network ls/inspect are allowed", 403)
            if "compose" in lowered and "ps" not in lowered:
                raise AppError("Only docker compose ps is allowed", 403)
        if executable == "journalctl":
            forbidden = ("--file", "--directory", "--root", "--image", "--machine")
            if any(token == name or token.startswith(f"{name}=")
                   for token in lowered for name in forbidden):
                raise AppError("journalctl file and alternate-root options are forbidden", 403)
        if executable == "systemctl" and any(
            token == "--root" or token.startswith("--root=") or token == "--image"
            or token.startswith("--image=") for token in lowered
        ):
            raise AppError("systemctl alternate-root options are forbidden", 403)
        if executable == "kubectl" and any(item in lowered for item in (
            "delete", "apply", "create", "edit", "exec", "patch", "replace", "scale",
        )):
            raise AppError("Mutating kubectl operations are forbidden", 403)
        if executable == "kubectl" and any(
            token in {"secret", "secrets", "configmap", "configmaps"} for token in lowered
        ):
            raise AppError("Kubernetes secret-bearing resources are forbidden", 403)
