import asyncio
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import asyncssh
import structlog

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.domain.models import Server
from app.services.secret_manager import SecretManager
from app.services.local_simulation_adapter import LocalSimulationAdapter


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int


@dataclass(frozen=True)
class RawCommandResult:
    stdout: str
    stderr: str
    exit_status: int


class OutputLimitExceeded(Exception):
    def __init__(self, partial: str) -> None:
        self.partial = partial
        super().__init__("SSH output limit exceeded")


class SshGateway:
    def __init__(self, secret_manager: SecretManager,
                 simulation_adapter: LocalSimulationAdapter | None = None,
                 settings: Settings | None = None) -> None:
        self.secret_manager = secret_manager
        self.settings = settings or get_settings()
        self.simulation_adapter = simulation_adapter

    async def execute(self, server: Server, command: str) -> CommandResult:
        if self.simulation_adapter is not None:
            start = perf_counter()
            result = await asyncio.wait_for(
                self.simulation_adapter.execute(server, command),
                timeout=self.settings.ssh_command_timeout_seconds,
            )
            return CommandResult(
                stdout=self._limit(result.stdout), stderr=self._limit(result.stderr),
                exit_code=result.exit_status,
                duration_ms=int((perf_counter() - start) * 1000),
            )
        if server.credential is None:
            raise AppError("Server has no credential reference", 400)
        credential = self.secret_manager.decrypt(server.credential.encrypted_payload)
        start = perf_counter()
        result = None
        for attempt in range(1, self.settings.ssh_max_attempts + 1):
            try:
                result = await asyncio.wait_for(
                    self._execute_asyncssh(server, credential, command),
                    timeout=self.settings.ssh_command_timeout_seconds
                    + self.settings.ssh_connect_timeout_seconds,
                )
                break
            except TimeoutError as exc:
                if attempt == self.settings.ssh_max_attempts:
                    raise AppError("SSH command timed out", 504) from exc
            except (asyncssh.Error, OSError) as exc:
                structlog.get_logger("ssh_gateway").warning(
                    "ssh_attempt_failed",
                    server_id=server.id,
                    attempt=attempt,
                    error_type=type(exc).__name__,
                )
                if attempt == self.settings.ssh_max_attempts:
                    raise AppError("SSH gateway could not connect to target", 502) from exc
            await asyncio.sleep(min(attempt, 2))
        if result is None:
            raise AppError("SSH gateway execution failed", 502)
        duration_ms = int((perf_counter() - start) * 1000)
        stdout = self._limit(result.stdout or "")
        stderr = self._limit(result.stderr or "")
        return CommandResult(
            stdout=stdout, stderr=stderr, exit_code=result.exit_status, duration_ms=duration_ms
        )

    async def _execute_asyncssh(self, server: Server, credential: dict[str, Any], command: str):
        username = credential.get("username")
        if not username:
            raise AppError("Credential is missing username", 500)
        options: dict[str, Any] = {
            "host": server.ip_address,
            "username": username,
            "port": int(server.ssh_config.get("port", 22)),
            "known_hosts": server.ssh_config.get("known_hosts")
            or self.settings.ssh_known_hosts_file,
            "connect_timeout": self.settings.ssh_connect_timeout_seconds,
        }
        if password := credential.get("password"):
            options["password"] = password
        if private_key := credential.get("private_key"):
            options["client_keys"] = [asyncssh.import_private_key(private_key)]
        async with asyncssh.connect(**options) as connection:
            process = await connection.create_process(command)
            stdout_task = asyncio.create_task(self._read_limited(process.stdout))
            stderr_task = asyncio.create_task(self._read_limited(process.stderr))
            wait_task = asyncio.create_task(process.wait_closed())
            try:
                stdout, stderr, _ = await asyncio.gather(
                    stdout_task,
                    stderr_task,
                    wait_task,
                )
            except OutputLimitExceeded as exc:
                process.kill()
                await process.wait_closed()
                for task in (stdout_task, stderr_task, wait_task):
                    if not task.done():
                        task.cancel()
                raise AppError("SSH output exceeded the configured limit", 413) from exc
            return RawCommandResult(
                stdout=stdout,
                stderr=stderr,
                exit_status=process.exit_status if process.exit_status is not None else -1,
            )

    async def _read_limited(self, stream) -> str:
        limit = self.settings.ssh_output_limit_bytes // 2
        chunks: list[str] = []
        size = 0
        while True:
            chunk = await stream.read(32 * 1024)
            if not chunk:
                return "".join(chunks)
            encoded = chunk.encode("utf-8")
            size += len(encoded)
            if size > limit:
                remaining = max(0, limit - (size - len(encoded)))
                chunks.append(encoded[:remaining].decode("utf-8", errors="replace"))
                raise OutputLimitExceeded("".join(chunks))
            chunks.append(chunk)

    def _limit(self, value: str) -> str:
        value = self._redact(value)
        limit = self.settings.ssh_output_limit_bytes
        encoded = value.encode("utf-8")
        if len(encoded) <= limit:
            return value
        return encoded[:limit].decode("utf-8", errors="replace") + "\n[output truncated]"

    @staticmethod
    def _redact(value: str) -> str:
        patterns = (
            r"(?i)\b(password|passwd|pwd|api[_-]?key|access[_-]?token|secret)\b"
            r"(\s*[:=]\s*)([^\s,;]+)",
            r"(?i)\b(authorization\s*:\s*bearer\s+)([^\s]+)",
        )
        safe = value
        for pattern in patterns:
            safe = re.sub(pattern, lambda match: f"{match.group(1)}{match.group(2) if match.lastindex and match.lastindex > 2 else ''}[REDACTED]", safe)
        return safe
