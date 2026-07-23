from time import perf_counter
import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import AIGateway, tool_definitions
from app.ai.models import AIMessage as ProviderMessage
from app.ai.models import ChatRequest, ToolCall
from app.core.exceptions import AppError, ApprovalRequired
from app.core.config import get_settings
from app.domain.models import AiMessage, AiSession, ApprovalRequest, Server, User
from app.domain.models.enums import ApprovalStatus
from app.services.audit_service import AuditService
from app.services.operation_service import OperationService
from app.services.ai_session_manager import AiSessionManager
from app.services.memory_service import MemoryService
from app.services.ssh_gateway import SshGateway
from app.services.tool_registry import ToolRegistry
from app.services.tool_configuration_service import list_effective_tools
from app.workspace import WorkspaceBuilder, WorkspaceContextBuilder


class AiService:
    def __init__(
        self,
        session: AsyncSession,
        gateway: AIGateway,
        registry: ToolRegistry,
        ssh_gateway: SshGateway,
    ) -> None:
        self.session = session
        self.gateway = gateway
        self.registry = registry
        self.ssh_gateway = ssh_gateway

    async def chat(
        self,
        *,
        user: User,
        message: str,
        session_id: str | None,
        system_id: str | None,
        server_id: str | None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        include_full_memory: bool | None = None,
        internal_continuation: bool = False,
        request_id: str | None = None,
        progress: Callable[[str, dict], Awaitable[None]] | None = None,
    ) -> dict:
        started = perf_counter()
        request_id = request_id or str(uuid4())
        server = await self._server(server_id, system_id)
        effective_system_id = server.system_id if server else system_id
        ai_session = await self._session(user, message, session_id, effective_system_id)
        if model is not None:
            ai_session.model = model.strip() or None
        if reasoning_effort is not None:
            ai_session.reasoning_effort = reasoning_effort
        if include_full_memory is not None:
            ai_session.include_full_memory = include_full_memory
        effective_system_id = effective_system_id or ai_session.system_id
        target_servers = list((await self.session.scalars(
            select(Server).where(Server.system_id == effective_system_id).order_by(Server.hostname)
        )).all()) if effective_system_id else []
        target_servers_by_id = {item.id: item for item in target_servers}
        if progress:
            await progress("session_ready", {"session_id": ai_session.id,
                                              "system_id": effective_system_id})
        workspace = WorkspaceBuilder(self.session)
        if progress:
            await progress("context_started", {"label": "Building scoped workspace context"})
        context = await WorkspaceContextBuilder(self.session, workspace).build(
            system_id=effective_system_id, server_id=server_id, message=message,
            session_id=ai_session.id, provider_session_id=ai_session.provider_session_id,
            include_full_memory=ai_session.include_full_memory,
            force_workspace_reload=bool((ai_session.memory or {}).get("workspace_reload_required")),
        )
        if progress:
            await progress("context_ready", {"sources": list(context.sources),
                                              "context_size": len(context.content),
                                              "bootstrap": context.bootstrap,
                                              "workspace_revision": context.revision})
        effective_tools = await list_effective_tools(self.session, self.registry)
        definitions = list(tool_definitions(self.registry, effective_tools))
        ai_tool_names = {tool.name for tool in self.registry.all()}
        if server is None:
            scoped_definitions = []
            target_description = "; ".join(
                f"{item.id}={item.hostname} ({item.ip_address})" for item in target_servers
            )
            for definition in definitions:
                if definition.name not in ai_tool_names:
                    scoped_definitions.append(definition)
                    continue
                parameters = dict(definition.parameters)
                properties = dict(parameters.get("properties", {}))
                properties["server_id"] = {
                    "type": "string", "enum": list(target_servers_by_id),
                    "description": f"Server in the selected System: {target_description}",
                }
                parameters["properties"] = properties
                parameters["required"] = [
                    *list(parameters.get("required", [])), "server_id"
                ]
                scoped_definitions.append(definition.model_copy(update={"parameters": parameters}))
            definitions = scoped_definitions
        request = ChatRequest(
            request_id=request_id,
            session_id=ai_session.id,
            messages=(ProviderMessage(role="system", content=context.content),
                      ProviderMessage(role="user", content=message)),
            tools=tuple(definitions),
            metadata={"system_id": effective_system_id or "", "server_id": server_id or "",
                      "workspace_path": context.workspace_path or "",
                      "workspace_sources": ",".join(context.sources),
                      "reasoning_effort": ai_session.reasoning_effort,
                      "workspace_revision": context.revision or "",
                      "workspace_bootstrap": str(context.bootstrap).lower(),
                      **AiSessionManager.provider_metadata(ai_session)},
            model=ai_session.model,
        )
        if progress:
            await progress("prompt_prepared", {
                "model": ai_session.model or "provider default",
                "reasoning_effort": ai_session.reasoning_effort,
                "prompt": f"{context.content}\n\nuser: {message}",
            })

        async def execute(call: ToolCall) -> dict:
            if call.name not in ai_tool_names:
                return {"action": call.name, "decision": "rejected",
                        "error": "AI may call only controlled SSH Gateway tools"}
            arguments = dict(call.arguments)
            target_server = server
            if target_server is None:
                target_server = target_servers_by_id.get(str(arguments.pop("server_id", "")))
                if target_server is None:
                    return {"error": "Select a valid server_id from the scoped tool contract",
                            "action": call.name, "decision": "rejected"}
            try:
                return await OperationService(self.session, self.registry, self.ssh_gateway).execute_tool(
                    user=user, server=target_server, action=call.name, arguments=arguments,
                    reason=f"AI-assisted operation requested by {user.email}",
                    session_id=ai_session.id,
                    bypass_policy=ai_session.bypass_policy,
                )
            except ApprovalRequired as exc:
                approval = await self.session.get(ApprovalRequest, exc.approval_id)
                consent = bool(approval and approval.plan.get("kind") == "ai_command_consent")
                if consent:
                    if progress is None:
                        return {"action": call.name, "decision": "command_consent_required",
                                "approval_id": exc.approval_id,
                                "server_id": target_server.id,
                                "error": "Use the streaming API to resume this task after consent"}
                    if progress:
                        await progress("command_consent_required", {
                            "approval_id": exc.approval_id,
                            "command": approval.plan.get("command"),
                            "server_id": target_server.id,
                            "hostname": target_server.hostname,
                        })
                    result = await self._wait_for_command_consent(approval)
                    await self.session.refresh(ai_session, attribute_names=[
                        "accept_all_commands"
                    ])
                    return result
                return {"action": call.name,
                        "decision": "approval_required",
                        "approval_id": exc.approval_id,
                        "command": None, "error": exc.message}
            except AppError as exc:
                return {"action": call.name, "decision": "rejected", "error": exc.message}

        if effective_system_id and context.workspace_path:
            manager = AiSessionManager(self.session)
            async with manager.active(
                ai_session, system_id=effective_system_id,
                workspace_path=context.workspace_path, context_size=len(context.content),
            ):
                result = await self.gateway.chat(request, tool_executor=execute,
                                                 progress=progress)
        else:
            result = await self.gateway.chat(request, tool_executor=execute, progress=progress)
        response = result.response
        AiSessionManager.accept_provider_session(ai_session, response.provider_session_id)
        confidence_score = response.confidence if response.confidence is not None else 0.65
        confidence = {
            "score": confidence_score,
            "reason": response.reasoning_summary or "Provider response with current session context.",
            "need_more_data": confidence_score < 0.8,
        }
        if not internal_continuation:
            self.session.add(AiMessage(session_id=ai_session.id, role="user", content=message))
        self.session.add(AiMessage(session_id=ai_session.id, role="assistant",
                                   content=response.content, tool_events=list(result.tool_events),
                                   confidence=confidence))
        memory = dict(ai_session.memory or {})
        memory["provider"] = response.provider
        memory["last_request_id"] = request.request_id
        memory["checked_tools"] = list(dict.fromkeys([
            *memory.get("checked_tools", []),
            *(event["tool"] for event in result.tool_events),
        ]))
        memory["workspace_revision"] = context.revision
        memory.pop("workspace_reload_required", None)
        ai_session.memory = memory
        if ai_session.title == "New conversation" and not internal_continuation:
            ai_session.title = message[:80]
        if progress:
            await progress("audit_started", {"label": "Recording immutable audit evidence"})
        provider_input = "\n\n".join(
            f"--- PROVIDER ROUND {index} ---\n{value}"
            for index, value in enumerate(result.provider_inputs, start=1)
        )
        await AuditService(self.session).record(
            user_id=user.id, session_id=ai_session.id, server_id=server.id if server else None,
            prompt=message, reasoning_summary=response.reasoning_summary,
            tool_name="ai_chat", ssh_command=None, output=response.content,
            decision="allow", duration_ms=int((perf_counter() - started) * 1000), result="success",
            provider_input=provider_input, provider=response.provider, model=response.model,
            request_id=request.request_id, context_sources=list(context.sources),
            tool_events=list(result.tool_events),
        )
        if effective_system_id:
            memory_events = [
                {
                    "tool": event.get("tool"),
                    "decision": event.get("result", {}).get("decision"),
                    "approval_id": event.get("result", {}).get("approval_id"),
                    "error": event.get("result", {}).get("error"),
                }
                for event in result.tool_events
            ]
            await MemoryService(self.session, workspace).record(
                system_id=effective_system_id, session_id=ai_session.id, request=message,
                answer=response.content, tool_events=memory_events, confidence=confidence,
                provider=response.provider, context_sources=context.sources,
            )
            await workspace.append_conversation(effective_system_id, ai_session.id, {
                "user_message": message, "ai_response": response.content,
                "tool_calls": memory_events, "audit_session_id": ai_session.id,
                "summary": response.reasoning_summary or response.content[:500],
            })
        await self.session.flush()
        if progress:
            await progress("persistence_completed", {
                "label": "Conversation, memory and audit saved",
                "tool_count": len(result.tool_events),
            })
        return {
            "session_id": ai_session.id, "request_id": request.request_id,
            "provider": response.provider, "model": response.model, "answer": response.content,
            "plan": ["Assess context", "Use registered tools when evidence is needed",
                     "Require approval for policy-controlled actions"],
            "executed_tools": list(result.tool_events), "confidence": confidence,
        }

    async def stream_chat(self, **kwargs) -> AsyncIterator[dict]:
        request_id = str(uuid4())
        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def report(event_type: str, data: dict) -> None:
            await queue.put({"type": event_type, "request_id": request_id, "data": data})

        await report("started", {"label": "Request accepted"})
        task = asyncio.create_task(self.chat(**kwargs, request_id=request_id, progress=report))
        heartbeat_at = asyncio.get_running_loop().time()
        while not task.done() or not queue.empty():
            try:
                yield await asyncio.wait_for(queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                now = asyncio.get_running_loop().time()
                if now - heartbeat_at >= 10:
                    heartbeat_at = now
                    yield {"type": "heartbeat", "request_id": request_id,
                           "data": {"status": "working"}}
                continue
        try:
            result = await task
        except Exception as exc:
            yield {"type": "error", "request_id": request_id,
                   "data": {"message": getattr(exc, "message", "AI request failed")}}
            return
        yield {"type": "content_delta", "request_id": request_id,
               "provider": result["provider"], "delta": result["answer"]}
        yield {"type": "completed", "request_id": request_id,
               "provider": result["provider"], "data": result}

    async def _session(self, user: User, message: str, session_id: str | None,
                       system_id: str | None) -> AiSession:
        if session_id is None:
            if system_id is None:
                raise AppError("Select a system before starting a conversation", 422)
            ai_session = AiSession(user_id=user.id, system_id=system_id, title=message[:80],
                                   memory={"checked_tools": []}, status="idle")
            self.session.add(ai_session)
            await self.session.flush()
            return ai_session
        ai_session = await self.session.get(AiSession, session_id)
        if ai_session is None or ai_session.user_id != user.id:
            raise AppError("AI session not found", 404)
        if ai_session.system_id and system_id and ai_session.system_id != system_id:
            raise AppError("AI session belongs to another system", 409)
        if ai_session.system_id is None:
            ai_session.system_id = system_id
        return ai_session

    async def _server(self, server_id: str | None, system_id: str | None) -> Server | None:
        if server_id is None:
            return None
        server = await self.session.get(Server, server_id)
        if server is None or (system_id and server.system_id != system_id):
            raise AppError("Server not found in the selected system", 404)
        return server

    async def _wait_for_command_consent(self, approval: ApprovalRequest) -> dict:
        timeout = get_settings().ai_command_consent_timeout_seconds
        deadline = asyncio.get_running_loop().time() + timeout
        try:
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.35)
                await self.session.refresh(approval, attribute_names=["status", "plan"])
                result = approval.plan.get("execution_result")
                if isinstance(result, dict):
                    return result
        except asyncio.CancelledError:
            approval.status = ApprovalStatus.expired
            approval.plan = {**approval.plan, "execution_result": {
                "action": "run_ssh_command", "decision": "cancelled",
                "approval_id": approval.id, "error": "AI execution was cancelled",
            }}
            await self.session.commit()
            raise
        approval.status = ApprovalStatus.expired
        approval.plan = {**approval.plan, "execution_result": {
            "action": "run_ssh_command", "decision": "expired",
            "approval_id": approval.id, "error": "Command consent timed out",
        }}
        await self.session.commit()
        return approval.plan["execution_result"]
