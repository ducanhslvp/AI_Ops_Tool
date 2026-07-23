import asyncio
import json
import os
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from time import monotonic, perf_counter

from app.ai.base import BaseProvider
from app.ai.config import ProviderConfig
from app.ai.errors import ProviderProtocolError, ProviderTimeoutError, ProviderUnavailableError
from app.ai.models import (
    ChatRequest, ChatResponse, ModelInfo, ProviderCapabilities, ProviderHealth, ProviderInfo,
    ProviderStatus, StreamEvent, StreamEventType, ToolCall,
)


class CodexProvider(BaseProvider):
    """Secure adapter for the documented ``codex exec`` JSONL transport."""

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__()
        self.model = config.model.strip() or "codex-cli-default"
        self._explicit_model = config.model.strip()
        self.executable = self._resolve_executable(config.executable or "codex")
        configured_allowlist = os.getenv("CODEX_EXECUTABLE_ALLOWLIST", "codex;codex.exe")
        allowed = {os.path.normcase(item.strip()) for item in configured_allowlist.split(";") if item.strip()}
        executable = os.path.normcase(self.executable)
        if executable not in allowed and os.path.normcase(Path(self.executable).name) not in allowed:
            raise ValueError("Codex executable is not in CODEX_EXECUTABLE_ALLOWLIST")
        self.timeout = config.timeout_seconds
        self.mode = config.mode or "cli"
        self.profile = str(config.extra.get("profile", "")).strip()
        self.codex_home = str(config.extra.get("codex_home", "")).strip()
        self.ephemeral = bool(config.extra.get("ephemeral", False))
        self.verify_authentication = bool(config.extra.get("verify_authentication", False))
        self.max_output_bytes = int(config.extra.get("max_output_bytes", 2_000_000))
        if not 64_000 <= self.max_output_bytes <= 10_000_000:
            raise ValueError("Codex max_output_bytes must be between 64000 and 10000000")
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._progress: dict[str, Callable[[str, dict], Awaitable[None]]] = {}
        self._model_cache: tuple[float, list[dict]] = (0.0, [])
        self._model_lock = asyncio.Lock()
        self._capabilities = ProviderCapabilities(
            streaming=False, tools=True, reasoning=True, mcp=False, local_execution=False
        )

    @staticmethod
    def _resolve_executable(configured: str) -> str:
        """Prefer the standalone Windows installation over the packaged app alias."""
        expanded = os.path.expandvars(os.path.expanduser(configured.strip()))
        if os.path.normcase(Path(expanded).name) not in {"codex", "codex.exe"}:
            return expanded
        if Path(expanded).is_absolute():
            return expanded
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            standalone = Path(local_app_data) / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"
            if standalone.is_file():
                return str(standalone)
        return expanded

    @staticmethod
    def _isolated_environment(codex_home: str = "") -> dict[str, str]:
        allowed = {
            "APPDATA", "CODEX_HOME", "HOME", "LOCALAPPDATA", "PATH", "SYSTEMROOT", "TEMP",
            "TMP", "USERPROFILE", "WINDIR",
        }
        environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        if codex_home:
            environment["CODEX_HOME"] = codex_home
        return environment

    @staticmethod
    def _process_options() -> dict[str, int]:
        if os.name == "nt":
            return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
        return {}

    async def _spawn(self, *arguments: str, cwd: str | None = None) -> asyncio.subprocess.Process:
        try:
            return await asyncio.create_subprocess_exec(
                self.executable, *arguments,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=self._isolated_environment(self.codex_home),
                **self._process_options(),
            )
        except PermissionError as exc:
            raise ProviderUnavailableError(
                "Codex CLI was found but the backend service account cannot execute it. "
                "Configure a standalone Codex CLI executable outside WindowsApps."
            ) from exc
        except OSError as exc:
            raise ProviderUnavailableError(
                "Codex CLI executable was not found or could not be started"
            ) from exc

    async def health_check(self) -> ProviderHealth:
        if self.mode != "cli":
            return ProviderHealth(provider="codex", status=ProviderStatus.degraded, model=self.model,
                                  detail=f"Transport {self.mode} is not supported")
        started = perf_counter()
        try:
            process = await self._spawn("--version")
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=8)
            if process.returncode != 0:
                raise ProviderUnavailableError(stderr.decode(errors="replace")[-500:])
            version = stdout.decode(errors="replace").strip() or "unknown"
            if self.verify_authentication:
                await self._authentication_probe()
        except ProviderUnavailableError as exc:
            detail = str(exc)
            status = (ProviderStatus.authentication_required
                      if any(word in detail.lower() for word in ("login", "auth", "credential"))
                      else ProviderStatus.disconnected)
            return ProviderHealth(provider="codex", status=status, model=self.model, detail=detail)
        except asyncio.TimeoutError:
            return ProviderHealth(provider="codex", status=ProviderStatus.disconnected,
                                  model=self.model, detail="Codex CLI connection check timed out")
        return ProviderHealth(provider="codex", status=ProviderStatus.ready, model=self.model,
                              version=version, latency_ms=int((perf_counter() - started) * 1000),
                              detail=f"Codex CLI {version} is ready at {self.executable}")

    def _runtime_arguments(self, request: ChatRequest) -> list[str]:
        arguments: list[str] = []
        model = (request.model or self._explicit_model).strip()
        if model:
            arguments.extend(["--model", model])
        effort = request.metadata.get("reasoning_effort", "medium").strip().lower()
        if effort not in {"low", "medium", "high", "xhigh", "max", "ultra"}:
            raise ProviderProtocolError("Unsupported Codex reasoning effort")
        arguments.extend(["--config", f'model_reasoning_effort="{effort}"'])
        return arguments

    def _base_exec_arguments(self, request: ChatRequest | None = None) -> list[str]:
        arguments = ["exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check"]
        if self.ephemeral:
            arguments.append("--ephemeral")
        if self.profile:
            arguments.extend(["--profile", self.profile])
        if request is not None:
            arguments.extend(self._runtime_arguments(request))
        elif self._explicit_model:
            arguments.extend(["--model", self._explicit_model])
        return arguments

    async def _authentication_probe(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aiops-codex-health-") as workspace:
            arguments = self._base_exec_arguments()
            if "--ephemeral" not in arguments:
                arguments.append("--ephemeral")
            process = await self._spawn(*arguments, "-", cwd=workspace)
            stdout, stderr = await asyncio.wait_for(process.communicate(b"Reply exactly READY."), timeout=30)
        if process.returncode != 0:
            detail = stderr.decode(errors="replace")[-800:].strip() or "authentication probe failed"
            raise ProviderUnavailableError(detail)
        if len(stdout) > self.max_output_bytes:
            raise ProviderUnavailableError("Codex CLI health response exceeded the output limit")

    @staticmethod
    def _output_schema() -> dict:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "answer": {"type": "string"},
                "reasoning_summary": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "tool_calls": {
                    "type": "array",
                    "items": {
                        "type": "object", "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "arguments_json": {"type": "string"},
                        },
                        "required": ["name", "arguments_json"],
                    },
                },
            },
            "required": ["answer", "reasoning_summary", "confidence", "tool_calls"],
        }

    def _prompt(self, request: ChatRequest) -> str:
        resumed = bool(request.metadata.get("provider_session_id"))
        bootstrap = request.metadata.get("workspace_bootstrap") == "true"
        trailing_tools = []
        for message in reversed(request.messages):
            if message.role != "tool":
                break
            trailing_tools.append(message)
        if resumed and trailing_tools:
            results = "\n".join(
                f"{message.name or 'run_ssh_command'}: {message.content}"
                for message in reversed(trailing_tools)
            )
            return (
                "BACKEND TOOL RESULT\n" + results
                + "\nContinue the current task. Request another registered backend tool only "
                  "when more infrastructure evidence or an approved operation is required."
            )

        transcript = "\n".join(f"{message.role}: {message.content}"
                               for message in request.messages)
        tools = [{"name": tool.name, "description": tool.description,
                  "parameters": tool.parameters} for tool in request.tools]
        registry = json.dumps(tools, ensure_ascii=True, separators=(",", ":"))
        if resumed and not bootstrap:
            return (
                "Continue the existing AIOps thread. The backend safety contract is unchanged. "
                f"Available backend tools: {registry}. "
                "never execute SSH directly.\n\nCURRENT TASK CONTEXT\n" + transcript
            )

        return (
            "You are the reasoning coordinator for an enterprise AIOps backend. You never execute "
            "SSH commands, open network connections, access files outside the isolated read-only "
            "workspace, or request credentials. Use only tools in the backend registry. The backend "
            "validates, authorizes, executes and audits every operation. Never invent another tool "
            "name or execute SSH directly. You may call registered tools repeatedly across targets "
            "when evidence or an approved change requires it. Return "
            "no tool calls when evidence is sufficient. Encode each tool's arguments as a JSON "
            "object string in arguments_json.\n\n"
            f"BACKEND TOOL REGISTRY:\n{registry}\n\n"
            f"CONVERSATION:\n{transcript}"
        )

    async def list_models(self, *, force: bool = False) -> list[dict]:
        """Read the signed-in CLI model catalog through the documented app-server protocol."""
        cached_at, cached = self._model_cache
        if not force and cached and monotonic() - cached_at < 300:
            return cached
        async with self._model_lock:
            cached_at, cached = self._model_cache
            if not force and cached and monotonic() - cached_at < 300:
                return cached
            catalog = await self._read_model_catalog()
            self._model_cache = (monotonic(), catalog)
            return catalog

    async def _read_model_catalog(self) -> list[dict]:
        process = await self._spawn("app-server")
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise ProviderProtocolError("Codex app-server pipes were not created")

        async def send(payload: dict) -> None:
            process.stdin.write((json.dumps(payload, separators=(",", ":")) + "\n").encode())
            await process.stdin.drain()

        async def response(request_id: int) -> dict:
            while True:
                line = await process.stdout.readline()
                if not line:
                    detail = (await process.stderr.read(2000)).decode(errors="replace")
                    raise ProviderProtocolError(
                        f"Codex app-server closed unexpectedly: {detail[-800:]}"
                    )
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("id") == request_id:
                    if payload.get("error"):
                        raise ProviderProtocolError(str(payload["error"]))
                    return payload.get("result") or {}

        try:
            await send({
                "method": "initialize", "id": 1,
                "params": {"clientInfo": {"name": "aiops-platform",
                                             "title": "AIOps Platform", "version": "1.0.0"},
                           "capabilities": {"experimentalApi": False}},
            })
            await asyncio.wait_for(response(1), timeout=10)
            await send({"method": "initialized"})
            models: list[dict] = []
            cursor: str | None = None
            request_id = 2
            while True:
                params: dict[str, object] = {"includeHidden": False, "limit": 100}
                if cursor:
                    params["cursor"] = cursor
                await send({"method": "model/list", "id": request_id, "params": params})
                result = await asyncio.wait_for(response(request_id), timeout=15)
                for item in result.get("data", []):
                    if not isinstance(item, dict) or item.get("hidden"):
                        continue
                    efforts = [
                        str(value.get("reasoningEffort"))
                        for value in item.get("supportedReasoningEfforts", [])
                        if isinstance(value, dict) and value.get("reasoningEffort")
                    ]
                    models.append({
                        "id": str(item.get("model") or item.get("id") or ""),
                        "display_name": str(item.get("displayName") or item.get("model") or ""),
                        "description": str(item.get("description") or ""),
                        "is_default": bool(item.get("isDefault")),
                        "default_reasoning_effort": str(
                            item.get("defaultReasoningEffort") or "medium"
                        ),
                        "reasoning_efforts": efforts or ["low", "medium", "high"],
                    })
                cursor = result.get("nextCursor")
                if not cursor:
                    break
                request_id += 1
            return [item for item in models if item["id"]]
        finally:
            if process.stdin and not process.stdin.is_closing():
                process.stdin.close()
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()

    def _resume_arguments(self, session_id: str, request: ChatRequest | None = None) -> list[str]:
        arguments = ["exec", "resume", "--json", "--skip-git-repo-check"]
        if self.profile:
            arguments.extend(["--profile", self.profile])
        if request is not None:
            arguments.extend(self._runtime_arguments(request))
        elif self._explicit_model:
            arguments.extend(["--model", self._explicit_model])
        arguments.append(session_id)
        return arguments

    async def _run(
        self, request: ChatRequest, provider_input: str | None = None
    ) -> tuple[list[dict], str | None]:
        if self.mode != "cli":
            raise ProviderUnavailableError(f"Unsupported Codex transport: {self.mode}")
        with tempfile.TemporaryDirectory(prefix="aiops-codex-") as workspace:
            schema_path = Path(workspace) / "response-schema.json"
            schema_path.write_text(json.dumps(self._output_schema()), encoding="utf-8")
            provider_session_id = request.metadata.get("provider_session_id", "").strip()
            arguments = (self._resume_arguments(provider_session_id, request) if provider_session_id
                         else self._base_exec_arguments(request))
            arguments.extend(["--output-schema", str(schema_path), "-"])
            requested_workspace = request.metadata.get("workspace_path", "")
            working_directory = Path(requested_workspace) if requested_workspace else Path(workspace)
            if not working_directory.is_dir() or working_directory.is_symlink():
                working_directory = Path(workspace)
            process = await self._spawn(*arguments, cwd=str(working_directory.resolve()))
            self._processes[request.request_id] = process
            try:
                actual_input = provider_input or self._prompt(request)
                progress = self._progress.get(request.request_id)
                if progress:
                    await progress("provider_input", {"prompt": actual_input,
                                                       "characters": len(actual_input)})
                stdout, stderr = await asyncio.wait_for(
                    self._communicate_streaming(
                        process, request, actual_input.encode()
                    ), timeout=self.timeout,
                )
            except asyncio.TimeoutError as exc:
                process.kill()
                await process.wait()
                raise ProviderTimeoutError("Codex CLI timed out") from exc
            finally:
                self._processes.pop(request.request_id, None)
        if len(stdout) > self.max_output_bytes or len(stderr) > self.max_output_bytes:
            raise ProviderProtocolError("Codex CLI output exceeded the configured limit")
        events: list[dict] = []
        for line in stdout.decode(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        if process.returncode != 0:
            detail = stderr.decode(errors="replace")[-1000:].strip()
            if not detail:
                failures = [event for event in events if event.get("type") in {"error", "turn.failed"}]
                if failures:
                    failure = failures[-1]
                    detail = str(failure.get("message") or failure.get("error") or failure)
            if provider_session_id:
                metadata = dict(request.metadata)
                metadata.pop("provider_session_id", None)
                retry_request = request.model_copy(update={"metadata": metadata})
                return await self._run(retry_request, self._prompt(retry_request))
            raise ProviderUnavailableError(f"Codex CLI failed: {detail or 'unknown CLI error'}")
        thread_id = next((str(event.get("thread_id")) for event in events
                          if event.get("type") == "thread.started" and event.get("thread_id")), None)
        return events, thread_id or provider_session_id or None

    async def _communicate_streaming(
        self, process: asyncio.subprocess.Process, request: ChatRequest, payload: bytes
    ) -> tuple[bytes, bytes]:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise ProviderProtocolError("Codex CLI process pipes were not created")
        process.stdin.write(payload)
        await process.stdin.drain()
        process.stdin.close()

        async def stdout_reader() -> bytes:
            chunks: list[bytes] = []
            size = 0
            while True:
                line = await process.stdout.readline()
                if not line:
                    return b"".join(chunks)
                size += len(line)
                if size > self.max_output_bytes:
                    raise ProviderProtocolError("Codex CLI output exceeded the configured limit")
                chunks.append(line)
                try:
                    event = json.loads(line.decode(errors="replace"))
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    await self._report_cli_event(request.request_id, event)

        async def stderr_reader() -> bytes:
            data = await process.stderr.read(self.max_output_bytes + 1)
            if len(data) > self.max_output_bytes:
                raise ProviderProtocolError("Codex CLI error output exceeded the configured limit")
            return data

        stdout, stderr, _ = await asyncio.gather(stdout_reader(), stderr_reader(), process.wait())
        return stdout, stderr

    async def _report_cli_event(self, request_id: str, event: dict) -> None:
        progress = self._progress.get(request_id)
        if progress is None:
            return
        event_type = str(event.get("type") or "codex_event")
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        item_type = str(item.get("type") or "")
        if event_type in {"thread.started", "turn.started", "turn.completed", "turn.failed"}:
            await progress("codex_status", {"status": event_type,
                                             "thread_id": event.get("thread_id")})
        elif item_type == "agent_message" and item.get("text"):
            await progress("codex_output", {"text": str(item["text"])[:20_000]})
        elif item_type:
            detail = str(item.get("command") or item.get("name") or item_type)[:1000]
            await progress("codex_activity", {"status": event_type, "activity": item_type,
                                               "detail": detail})

    @staticmethod
    def _payload(events: list[dict]) -> dict:
        messages: list[str] = []
        for event in events:
            item = event.get("item") or {}
            if item.get("type") == "agent_message" and item.get("text"):
                messages.append(item["text"])
            elif event.get("type") == "message" and event.get("content"):
                messages.append(str(event["content"]))
        if not messages:
            raise ProviderProtocolError("Codex CLI returned no agent message")
        try:
            payload = json.loads(messages[-1])
        except (json.JSONDecodeError, TypeError) as exc:
            raise ProviderProtocolError("Codex CLI returned an invalid structured response") from exc
        if not isinstance(payload, dict):
            raise ProviderProtocolError("Codex CLI response must be an object")
        return payload

    async def chat(self, request: ChatRequest) -> ChatResponse:
        provider_input = self._prompt(request)
        events, provider_session_id = await self._run(request, provider_input)
        payload = self._payload(events)
        allowed_tools = {tool.name for tool in request.tools}
        calls: list[ToolCall] = []
        for item in payload.get("tool_calls", []):
            if item.get("name") not in allowed_tools:
                continue
            try:
                arguments = json.loads(item.get("arguments_json", "{}"))
            except json.JSONDecodeError as exc:
                raise ProviderProtocolError("Codex CLI returned invalid tool arguments JSON") from exc
            if not isinstance(arguments, dict):
                raise ProviderProtocolError("Codex CLI tool arguments must be an object")
            calls.append(ToolCall(name=item["name"], arguments=arguments))
        return ChatResponse(
            request_id=request.request_id, provider="codex", model=request.model or self.model,
            content=str(payload.get("answer", "")),
            reasoning_summary=str(payload.get("reasoning_summary", "")) or None,
            tool_calls=tuple(calls), confidence=float(payload.get("confidence", 0.7)),
            finish_reason="tool_calls" if calls else "stop", provider_session_id=provider_session_id,
            provider_input=provider_input,
        )

    async def chat_with_progress(
        self, request: ChatRequest, progress: Callable[[str, dict], Awaitable[None]]
    ) -> ChatResponse:
        self._progress[request.request_id] = progress
        try:
            return await self.chat(request)
        finally:
            self._progress.pop(request.request_id, None)

    async def _stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type=StreamEventType.started, request_id=request.request_id,
                          provider="codex", data={"transport": "cli"})
        response = await self.chat(request)
        yield StreamEvent(type=StreamEventType.content_delta, request_id=request.request_id,
                          provider="codex", delta=response.content)
        yield StreamEvent(type=StreamEventType.completed, request_id=request.request_id,
                          provider="codex", data={"finish_reason": response.finish_reason})

    def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        return self._stream(request)

    async def cancel(self, request_id: str) -> bool:
        process = self._processes.get(request_id)
        if process is None:
            return await super().cancel(request_id)
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except asyncio.TimeoutError:
            process.kill()
        return True

    async def close(self) -> None:
        for request_id in list(self._processes):
            await self.cancel(request_id)
        await super().close()

    def get_model_info(self) -> ModelInfo:
        return ModelInfo(provider="codex", model=self.model, capabilities=self._capabilities)

    def get_provider_info(self) -> ProviderInfo:
        return ProviderInfo(name="codex", display_name="OpenAI Codex CLI", transport=self.mode,
                            capabilities=self._capabilities)
