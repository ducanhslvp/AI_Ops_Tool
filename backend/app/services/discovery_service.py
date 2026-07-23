from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import AIGateway
from app.ai.models import AIMessage as ProviderMessage
from app.ai.models import ChatRequest
from app.core.exceptions import AppError
from app.domain.models import (
    AiMessage, AiSession, DiscoveryScan, DiscoverySchedule, KnowledgeDocument,
    Server, System, User,
)
from app.schemas.discovery import DiscoveryCreate
from app.services.operation_service import OperationService
from app.services.plugins.discovery import DISCOVERY_PLUGINS, build_dependency_edges
from app.services.ssh_gateway import SshGateway
from app.services.tool_registry import ToolRegistry
from app.workspace import WorkspaceBuilder

DISCOVERY_ACTIONS = (
    "system_information", "hardware_information", "check_network",
    "list_filesystems", "list_services", "list_connections", "list_deployed_applications",
    "docker_inventory", "kubernetes_inventory",
)


class DiscoveryService:
    def __init__(self, session: AsyncSession, registry: ToolRegistry, gateway: SshGateway,
                 ai_gateway: AIGateway | None = None) -> None:
        self.session = session
        self.registry = registry
        self.operations = OperationService(session, registry, gateway)
        self.ai_gateway = ai_gateway

    async def run(self, payload: DiscoveryCreate, user: User) -> DiscoveryScan:
        servers = await self._resolve_servers(payload)
        baseline = await self._baseline(payload)
        scan = DiscoveryScan(
            requested_by_user_id=user.id, system_id=payload.system_id,
            baseline_scan_id=baseline.id if baseline else None,
            scope_type="system" if payload.system_id else "servers",
            server_ids=[server.id for server in servers], status="running",
            options=payload.options.model_dump(), started_at=datetime.now(UTC),
        )
        self.session.add(scan)
        await self.session.flush()
        evidence_by_server: dict[str, dict[str, str]] = {}
        nodes: list[dict[str, Any]] = []
        failures = 0
        for server in servers:
            evidence: dict[str, str] = {}
            for action in DISCOVERY_ACTIONS:
                tool = self.registry.get(action)
                if not self.registry.supports_target(tool, server.server_type, server.os):
                    continue
                try:
                    result = await self.operations.execute_tool(
                        user=user, server=server, action=action, arguments={},
                        reason=f"Infrastructure discovery scan {scan.id}", session_id=scan.id,
                    )
                    evidence[action] = self._sanitize(
                        result.get("stdout") or result.get("stderr") or ""
                    )
                except AppError as exc:
                    evidence[f"{action}_error"] = exc.message
                    failures += 1
            evidence_by_server[server.id] = evidence
            node = self._base_node(server)
            for plugin in DISCOVERY_PLUGINS:
                plugin.enrich(node, evidence, payload.options.include_system_services)
            nodes.append(node)
        edges = build_dependency_edges(nodes, evidence_by_server)
        ai_analysis: dict[str, Any] | None = None
        if self.ai_gateway is not None:
            try:
                ai_analysis = await self._analyze_with_ai(
                    scan=scan, user=user, servers=servers, nodes=nodes, edges=edges)
                edges = self._merge_ai_edges(nodes, edges, ai_analysis)
                evidence_by_server["_ai_analysis"] = {
                    "provider": str(ai_analysis.get("provider", "")),
                    "model": str(ai_analysis.get("model", "")),
                    "summary": str(ai_analysis.get("summary", "")),
                    "risks": json.dumps(ai_analysis.get("risks", []), ensure_ascii=True),
                }
            except Exception as exc:
                evidence_by_server["_ai_analysis"] = {
                    "error": type(exc).__name__,
                    "summary": "AI analysis was unavailable; the validated collector graph was retained.",
                }
                failures += 1
        scan.nodes = nodes
        scan.edges = edges
        scan.raw_evidence = evidence_by_server
        scan.change_summary = self._diff(baseline, nodes, edges)
        deterministic_summary = self._summary(nodes, edges, failures)
        scan.summary = str(ai_analysis.get("summary")) if ai_analysis and ai_analysis.get(
            "summary") else deterministic_summary
        scan.status = "partial" if failures else "completed"
        scan.completed_at = datetime.now(UTC)
        await self._update_knowledge(scan, servers)
        await self.session.flush()
        workspace = WorkspaceBuilder(self.session)
        for system_id in sorted({server.system_id for server in servers}):
            await workspace.sync_system(system_id)
        await self.session.commit()
        await self.session.refresh(scan)
        return scan

    async def _analyze_with_ai(
        self, *, scan: DiscoveryScan, user: User, servers: list[Server],
        nodes: list[dict[str, Any]], edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        system_id = scan.system_id or servers[0].system_id
        system = await self.session.get(System, system_id)
        if system is None:
            raise AppError("Discovery System context no longer exists", 409)
        evidence = {
            "scan_id": scan.id,
            "system": {"id": system.id, "code": system.code, "name": system.name},
            "nodes": [{"id": node["id"], **node["data"]} for node in nodes],
            "detected_dependencies": edges,
        }
        task = (
            "Analyze this sanitized infrastructure discovery snapshot. Return JSON only with "
            "keys summary (string), risks (string array), and dependencies (array). Each "
            "dependency must contain source_id, target_id, port, protocol, connection_type, "
            "service_name and confidence. Use only node IDs present in the input. Do not "
            "invent hosts, credentials, commands, or secrets.\n\n"
            f"{json.dumps(evidence, ensure_ascii=True, default=str)}"
        )
        ai_session = AiSession(
            user_id=user.id, system_id=system.id,
            title=f"Discovery analysis - {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            memory={"kind": "infrastructure_discovery", "scan_id": scan.id},
            status="running", reasoning_effort="medium",
        )
        self.session.add(ai_session)
        await self.session.flush()
        request = ChatRequest(
            session_id=ai_session.id,
            messages=(
                ProviderMessage(role="system", content=(
                    "You are the infrastructure discovery analyst. Analyze evidence only. "
                    "Never request or execute tools in this analysis phase.")),
                ProviderMessage(role="user", content=task),
            ),
            metadata={
                "system_id": system.id, "discovery_scan_id": scan.id,
                "reasoning_effort": "medium",
            },
        )
        try:
            result = await self.ai_gateway.chat(request)
        except Exception:
            ai_session.status = "failed"
            ai_session.last_activity_at = datetime.now(UTC)
            await self.session.flush()
            raise
        response = result.response
        parsed = self._parse_ai_json(response.content)
        parsed["provider"] = response.provider
        parsed["model"] = response.model
        ai_session.status = "idle"
        ai_session.provider_session_id = response.provider_session_id
        ai_session.last_activity_at = datetime.now(UTC)
        ai_session.memory = {
            **ai_session.memory, "provider": response.provider, "model": response.model,
            "summary": str(parsed.get("summary", ""))[:4000],
        }
        self.session.add(AiMessage(session_id=ai_session.id, role="user", content=task))
        self.session.add(AiMessage(
            session_id=ai_session.id, role="assistant", content=response.content,
            confidence={
                "score": response.confidence if response.confidence is not None else 0.7,
                "reason": response.reasoning_summary or "AI analysis of sanitized discovery evidence.",
                "need_more_data": response.confidence is not None and response.confidence < 0.8,
            },
        ))
        return parsed

    @staticmethod
    def _parse_ai_json(content: str) -> dict[str, Any]:
        value = content.strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.I)
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", value, flags=re.S)
            if not match:
                return {"summary": content[:4000], "risks": [], "dependencies": []}
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return {"summary": content[:4000], "risks": [], "dependencies": []}
        if not isinstance(parsed, dict):
            return {"summary": content[:4000], "risks": [], "dependencies": []}
        return {
            "summary": str(parsed.get("summary", ""))[:8000],
            "risks": parsed.get("risks", []) if isinstance(parsed.get("risks"), list) else [],
            "dependencies": parsed.get("dependencies", [])
            if isinstance(parsed.get("dependencies"), list) else [],
        }

    @staticmethod
    def _merge_ai_edges(
        nodes: list[dict[str, Any]], edges: list[dict[str, Any]],
        analysis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        node_ids = {str(node["id"]) for node in nodes}
        merged = list(edges)
        signatures = {(str(edge.get("source")), str(edge.get("target")),
                       str(edge.get("port", ""))) for edge in edges}
        for candidate in analysis.get("dependencies", []):
            if not isinstance(candidate, dict):
                continue
            source = str(candidate.get("source_id", ""))
            target = str(candidate.get("target_id", ""))
            port = str(candidate.get("port", ""))
            if source not in node_ids or target not in node_ids or source == target:
                continue
            signature = (source, target, port)
            if signature in signatures:
                continue
            digest = sha256("|".join(signature).encode("utf-8")).hexdigest()[:16]
            merged.append({
                "id": f"ai-{digest}", "source": source, "target": target,
                "port": int(port) if port.isdigit() else 0,
                "protocol": str(candidate.get("protocol", "tcp"))[:20],
                "connection_type": str(candidate.get(
                    "connection_type", "ai_inferred"))[:80],
                "service_name": str(candidate.get("service_name", ""))[:120],
                "confidence": candidate.get("confidence") if isinstance(
                    candidate.get("confidence"), (int, float)) else 0.5,
                "reason": "AI-inferred from sanitized discovery evidence",
            })
            signatures.add(signature)
        return merged

    async def run_schedule(self, schedule: DiscoverySchedule, user: User) -> DiscoveryScan:
        payload = DiscoveryCreate(
            system_id=schedule.system_id, server_ids=schedule.server_ids,
            options={"incremental": schedule.incremental,
                     "include_system_services": schedule.include_system_services},
        )
        scan = await self.run(payload, user)
        schedule.last_run_at = datetime.now(UTC)
        schedule.next_run_at = schedule.last_run_at + timedelta(minutes=schedule.interval_minutes)
        await self.session.commit()
        return scan

    async def _resolve_servers(self, payload: DiscoveryCreate) -> list[Server]:
        statement = select(Server).order_by(Server.hostname)
        if payload.system_id:
            if await self.session.get(System, payload.system_id) is None:
                raise AppError("System not found", 404)
            statement = statement.where(Server.system_id == payload.system_id)
        else:
            statement = statement.where(Server.id.in_(payload.server_ids))
        servers = list((await self.session.scalars(statement)).all())
        if not servers or (payload.server_ids and len(servers) != len(set(payload.server_ids))):
            raise AppError("One or more discovery targets do not exist", 422)
        return servers

    async def _baseline(self, payload: DiscoveryCreate) -> DiscoveryScan | None:
        statement = select(DiscoveryScan).where(DiscoveryScan.status.in_(["completed", "partial"]))
        if payload.system_id:
            statement = statement.where(DiscoveryScan.system_id == payload.system_id)
            return await self.session.scalar(statement.order_by(
                DiscoveryScan.completed_at.desc()).limit(1))
        candidates = list((await self.session.scalars(statement.where(
            DiscoveryScan.scope_type == "servers").order_by(
                DiscoveryScan.completed_at.desc()).limit(20))).all())
        requested = set(payload.server_ids)
        return next((candidate for candidate in candidates
                     if set(candidate.server_ids) == requested), None)

    @staticmethod
    def _sanitize(value: str) -> str:
        patterns = (
            r"(?i)(password|passwd|pwd)(\s*[=:]\s*)[^\s,;]+",
            r"(?i)(token|api[_-]?key|secret)(\s*[=:]\s*)[^\s,;]+",
            r"(?i)(authorization:\s*(?:bearer|basic)\s+)[A-Za-z0-9._~+/=-]+",
        )
        sanitized = value
        for pattern in patterns:
            sanitized = re.sub(pattern, lambda match: f"{match.group(1)}{match.group(2) if match.lastindex and match.lastindex > 1 else ''}[REDACTED]", sanitized)
        return sanitized

    @staticmethod
    def _base_node(server: Server) -> dict[str, Any]:
        return {"id": server.id, "type": "server", "data": {
            "hostname": server.hostname, "ip": server.ip_address, "os": server.os,
            "server_type": server.server_type, "role": server.role, "health": server.status,
            "system_id": server.system_id, "system": server.system.code,
            "environment_id": server.environment_id, "environment": server.environment.name,
            "description": server.description, "tags": server.tags,
        }}

    @staticmethod
    def _diff(baseline: DiscoveryScan | None, nodes: list[dict], edges: list[dict]) -> dict:
        if baseline is None:
            return {"baseline": False, "added_nodes": [item["id"] for item in nodes],
                    "removed_nodes": [], "changed_nodes": [],
                    "added_edges": [item["id"] for item in edges], "removed_edges": []}
        old_nodes = {item["id"]: item for item in baseline.nodes}
        new_nodes = {item["id"]: item for item in nodes}
        old_edges = {item["id"] for item in baseline.edges}
        new_edges = {item["id"] for item in edges}
        return {"baseline": True, "added_nodes": sorted(new_nodes.keys() - old_nodes.keys()),
                "removed_nodes": sorted(old_nodes.keys() - new_nodes.keys()),
                "changed_nodes": sorted(key for key in new_nodes.keys() & old_nodes.keys()
                                        if new_nodes[key] != old_nodes[key]),
                "added_edges": sorted(new_edges - old_edges),
                "removed_edges": sorted(old_edges - new_edges)}

    @staticmethod
    def _summary(nodes: list[dict], edges: list[dict], failures: int) -> str:
        unhealthy = sum(node["data"]["health"] != "online" for node in nodes)
        containers = sum(len(node["data"].get("containers", [])) for node in nodes)
        resources = sum(len(node["data"].get("kubernetes_resources", [])) for node in nodes)
        return (f"Discovered {len(nodes)} servers, {len(edges)} dependencies, {containers} "
                f"containers and {resources} Kubernetes resources. {unhealthy} servers require "
                f"attention; {failures} collectors returned limited evidence.")

    async def _update_knowledge(self, scan: DiscoveryScan, servers: list[Server]) -> None:
        system_ids = {server.system_id for server in servers}
        for system_id in system_ids:
            system = await self.session.get(System, system_id)
            if system is None:
                continue
            title = f"Infrastructure Discovery - {system.code}"
            document = await self.session.scalar(select(KnowledgeDocument).where(
                KnowledgeDocument.system_id == system_id, KnowledgeDocument.title == title))
            system_nodes = [node for node in scan.nodes if node["data"]["system_id"] == system_id]
            node_ids = {node["id"] for node in system_nodes}
            system_edges = [edge for edge in scan.edges if edge["source"] in node_ids or
                            edge["target"] in node_ids]
            content = f"# {title}\n\n{scan.summary}\n\nSnapshot: `{scan.id}`"
            if document is None:
                document = KnowledgeDocument(system_id=system_id, title=title,
                    document_type="discovery_snapshot", source_uri=f"discovery://{scan.id}",
                    content_text=content, graph_nodes=system_nodes, graph_edges=system_edges)
                self.session.add(document)
            else:
                document.source_uri = f"discovery://{scan.id}"
                document.content_text = content
                document.graph_nodes = system_nodes
                document.graph_edges = system_edges
