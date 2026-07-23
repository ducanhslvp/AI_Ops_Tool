import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models import DiscoveryScan, KnowledgeDocument, PolicyRule, Report, Server, System
from app.services.tool_configuration_service import list_effective_tools
from app.services.tool_registry import ToolRegistry
from app.workspace.storage import LocalWorkspaceStorage, WorkspaceStorage

_SYSTEM_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,39}$")
_SENSITIVE_VALUE = re.compile(
    r"(?i)(password|passwd|private[_ -]?key|access[_ -]?token|secret)\s*[:=]\s*([^\s,;]+)"
)
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(key: str) -> asyncio.Lock:
    return _locks.setdefault(key, asyncio.Lock())


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-").lower()
    return slug[:100] or fallback


def _redact_memory(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if re.search(r"(?i)password|passwd|private_key|token|secret", key)
            else _redact_memory(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_memory(item) for item in value]
    if isinstance(value, str):
        return _SENSITIVE_VALUE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    return value


class WorkspaceBuilder:
    """Builds a secret-free, deterministic filesystem projection of platform state."""

    directories = (
        "docs", "uploads", "runbooks", "skills", "memory", "memory/daily",
        "memory/incidents", "memory/operations", "memory/summaries", "memory/decisions",
        "memory/archive", "history", "generated", "conversations", "summaries",
        "discovery", "inventory", "context", "reports",
    )

    def __init__(self, session: AsyncSession, storage: WorkspaceStorage | None = None) -> None:
        self.session = session
        self.storage = storage or LocalWorkspaceStorage(get_settings().workspace_root)
        self.registry = ToolRegistry()

    @staticmethod
    def validate_system_code(code: str) -> str:
        if not _SYSTEM_CODE.fullmatch(code):
            raise ValueError("System code must contain only letters, numbers, underscore or hyphen")
        return code

    def workspace_relative(self, system: System) -> str:
        return self.validate_system_code(system.code)

    def workspace_path(self, system: System) -> Path:
        return self.storage.resolve(self.workspace_relative(system))

    async def sync_all(self) -> None:
        systems = list((await self.session.scalars(select(System).order_by(System.code))).all())
        for system in systems:
            await self.sync_system(system.id)

    async def sync_system(self, system_id: str) -> Path:
        system = await self.session.get(System, system_id)
        if system is None:
            raise ValueError("System does not exist")
        key = self.workspace_relative(system)
        async with _lock_for(key):
            for directory in self.directories:
                self.storage.resolve(f"{key}/{directory}").mkdir(parents=True, exist_ok=True)
            servers = list((await self.session.scalars(
                select(Server).where(Server.system_id == system.id).order_by(Server.hostname)
            )).all())
            policies = list((await self.session.scalars(
                select(PolicyRule).order_by(PolicyRule.priority, PolicyRule.name)
            )).all())
            documents = list((await self.session.scalars(
                select(KnowledgeDocument).where(KnowledgeDocument.system_id == system.id)
                .order_by(KnowledgeDocument.title)
            )).all())
            reports = list((await self.session.scalars(
                select(Report).where(Report.system_id == system.id)
                .order_by(Report.created_at.desc()).limit(20)
            )).all())
            latest_scan = await self.session.scalar(
                select(DiscoveryScan).where(
                    DiscoveryScan.system_id == system.id,
                    DiscoveryScan.status.in_(["completed", "partial"]),
                ).order_by(DiscoveryScan.completed_at.desc()).limit(1)
            )
            tools = await list_effective_tools(self.session, self.registry)
            await self._write_core(system, servers, policies, tools, latest_scan)
            await self._sync_documents(system, documents)
            await self._sync_skills(system, servers)
            await self._sync_reports(system, reports)
            await self._migrate_legacy_memory(system)
            await self.storage.write_text(f"{key}/.workspace-manifest.json", json.dumps({
                "schema_version": 2, "system_id": system.id, "system_code": system.code,
                "generated_at": datetime.now(UTC).isoformat(),
                "security": "secret-free projection",
            }, indent=2))
        return self.workspace_path(system)

    async def _write_core(self, system: System, servers: list[Server], policies: list[PolicyRule],
                          tools: list[Any], latest_scan: DiscoveryScan | None) -> None:
        key = self.workspace_relative(system)
        server_rows = [{
            "id": server.id, "hostname": server.hostname, "ip_address": server.ip_address,
            "os": server.os, "environment": server.environment.name,
            "server_type": server.server_type, "role": server.role,
            "description": server.description, "tags": server.tags, "status": server.status,
        } for server in servers]
        policy_rows = [{
            "name": rule.name, "effect": rule.effect, "priority": rule.priority,
            "role": rule.role, "environment": rule.environment, "server_type": rule.server_type,
            "action": rule.action, "risk_level": rule.risk_level,
            "time_window": rule.time_window, "active": rule.is_active,
        } for rule in policies]
        await self.storage.write_text(f"{key}/servers.yaml", yaml.safe_dump(
            {"system": system.code, "servers": server_rows}, sort_keys=False, allow_unicode=True))
        await self.storage.write_text(f"{key}/policy.yaml", yaml.safe_dump(
            {"system": system.code, "rules": policy_rows}, sort_keys=False, allow_unicode=True))
        tool_lines = ["# Backend Tool Contract", "", "AI may request only these actions. The backend applies RBAC, policy, approval and audit.", ""]
        for tool in tools:
            tool_lines.extend([
                f"## `{tool.name}()`", "", tool.description,
                f"- Plugin: `{tool.plugin}`", f"- Risk: `{tool.risk_level}`",
                f"- Targets: `{', '.join(tool.target_types)}`",
                f"- Arguments schema: `{json.dumps(tool.arguments_schema, sort_keys=True)}`", "",
            ])
        await self.storage.write_text(f"{key}/tools.md", "\n".join(tool_lines))
        await self.storage.write_text(f"{key}/README.md", (
            f"# {system.name} ({system.code})\n\n{system.description}\n\n"
            f"- Owner: {system.owner or 'Unassigned'}\n- Criticality: {system.criticality}\n"
            f"- Workspace schema: 1\n\n"
            "Read `system_prompt.md`, then relevant runbooks, architecture, inventory, policy and recent memory.\n"
        ))
        await self.storage.write_text(f"{key}/system_prompt.md", (
            f"# System Prompt: {system.code}\n\nYou are operating only system **{system.name}**.\n\n"
            "1. Read relevant files from this workspace; prioritize `runbooks/`.\n"
            "2. Never request, infer, expose or persist credentials, usernames, passwords, tokens, private keys or connection strings.\n"
            "3. Never execute SSH directly. Request only the structured SSH Gateway "
            "tools documented in `tools.md`.\n"
            "4. Treat `policy.yaml` as mandatory. Dangerous actions require backend approval.\n"
            "5. State confidence, evidence and missing data. Workspace files may be stale; check timestamps.\n"
            "6. The backend owns execution, security and audit. You own planning and interpretation only.\n"
        ))
        inventory = [f"# Inventory: {system.name}", "", "| Hostname | IP | Environment | OS | Type | Role | Status |", "|---|---|---|---|---|---|---|"]
        inventory.extend(f"| {s['hostname']} | {s['ip_address']} | {s['environment']} | {s['os']} | {s['server_type']} | {s['role']} | {s['status']} |" for s in server_rows)
        await self.storage.write_text(f"{key}/inventory.md", "\n".join(inventory) + "\n")
        await self._write_discovery(system, latest_scan)

    async def _write_discovery(self, system: System, scan: DiscoveryScan | None) -> None:
        key = self.workspace_relative(system)
        if scan is None:
            content = "No completed discovery snapshot is available.\n"
            for name in ("architecture.md", "topology.md", "dependencies.md", "services.md"):
                await self.storage.write_text(f"{key}/{name}", f"# {name[:-3].title()}\n\n{content}")
            return
        nodes = [node for node in scan.nodes if node.get("data", {}).get("system_id") == system.id]
        ids = {node.get("id") for node in nodes}
        edges = [edge for edge in scan.edges if edge.get("source") in ids or edge.get("target") in ids]
        await self.storage.write_text(f"{key}/architecture.md", (
            f"# Architecture\n\n{scan.summary}\n\nSnapshot: `{scan.id}`\n"
            f"Completed: `{scan.completed_at.isoformat() if scan.completed_at else 'unknown'}`\n"))
        topology = ["# Topology", "", "| Node | IP | Environment | Health | Services |", "|---|---|---|---|---|"]
        services: list[str] = ["# Deployed Services", ""]
        for node in nodes:
            data = node.get("data", {})
            deployed = data.get("services") or data.get("deployed_applications") or []
            topology.append(f"| {data.get('hostname', node.get('id'))} | {data.get('ip', '')} | {data.get('environment', '')} | {data.get('health', '')} | {', '.join(map(str, deployed))} |")
            services.extend([f"## {data.get('hostname', node.get('id'))}", "", json.dumps(deployed, ensure_ascii=False, indent=2), ""])
        dependencies = ["# Dependencies", "", "| Source | Destination | Port | Protocol | Type | Service | Confidence |", "|---|---|---|---|---|---|---|"]
        for edge in edges:
            dependencies.append(f"| {edge.get('source')} | {edge.get('target')} | {edge.get('port', '')} | {edge.get('protocol', '')} | {edge.get('connection_type', '')} | {edge.get('service_name', '')} | {edge.get('confidence', '')} |")
        await self.storage.write_text(f"{key}/topology.md", "\n".join(topology) + "\n")
        await self.storage.write_text(f"{key}/dependencies.md", "\n".join(dependencies) + "\n")
        await self.storage.write_text(f"{key}/services.md", "\n".join(services) + "\n")
        await self.storage.write_text(f"{key}/generated/discovery-{scan.id}.json", json.dumps({
            "summary": scan.summary, "nodes": nodes, "edges": edges,
            "change_summary": scan.change_summary,
        }, ensure_ascii=False, indent=2, default=str))

    async def _sync_documents(self, system: System, documents: list[KnowledgeDocument]) -> None:
        key = self.workspace_relative(system)
        for document in documents:
            if document.source_uri and not document.source_uri.startswith(("workspace://", "discovery://")):
                source = Path(document.source_uri).resolve()
                legacy_root = (Path.cwd() / "data" / "knowledge").resolve()
                if source.is_file() and source.parent == legacy_root:
                    uri = await self.store_upload(
                        system, document.id, source.name, await asyncio.to_thread(source.read_bytes),
                        document.content_text,
                    )
                    document.source_uri = uri
                    document.content_text = ""
            name = f"{_slug(document.title, document.id)}--{document.id}.md"
            directory = "runbooks" if document.document_type == "runbook" else "docs"
            if document.content_text:
                await self.storage.write_text(f"{key}/{directory}/{name}", (
                    f"---\nid: {document.id}\ntitle: {json.dumps(document.title)}\n"
                    f"type: {document.document_type}\nupdated_at: {document.updated_at.isoformat()}\n---\n\n"
                    f"{document.content_text}"
                ))

    async def _sync_skills(self, system: System, servers: list[Server]) -> None:
        key = self.workspace_relative(system)
        skill_names = {"network"}
        for server in servers:
            value = f"{server.os} {server.server_type} {server.role} {' '.join(server.tags)}".lower()
            skill_names.update(name for name in (
                "linux", "windows", "docker", "kubernetes", "oracle", "redis", "kafka"
            ) if name in value)
        for name in sorted(skill_names):
            await self.storage.write_text(f"{key}/skills/{name}.md", (
                f"# {name.title()} Operations Skill\n\n"
                "Use only backend-registered tools applicable to this target. Read the relevant runbook first, "
                "collect evidence before conclusions, and request approval for mutating actions.\n"
            ))

    async def _sync_reports(self, system: System, reports: list[Report]) -> None:
        key = self.workspace_relative(system)
        await self.storage.remove(f"{key}/reports", recursive=True)
        self.storage.resolve(f"{key}/reports").mkdir(parents=True, exist_ok=True)
        for report in reports:
            content = report.content if report.format == "markdown" else (
                f"Original format: `{report.format}`\n\n```text\n{report.content[:20_000]}\n```"
            )
            await self.storage.write_text(
                f"{key}/reports/{report.created_at:%Y%m%d}--{_slug(report.title, report.id)}--{report.id}.md",
                f"# {report.title}\n\n- Report ID: `{report.id}`\n"
                f"- Created: `{report.created_at.isoformat()}`\n\n{content}\n",
            )

    async def _migrate_legacy_memory(self, system: System) -> None:
        key = self.workspace_relative(system)
        memory_root = self.storage.resolve(f"{key}/memory")
        for source in memory_root.glob("*.json"):
            if source.is_symlink():
                continue
            destination = f"{key}/memory/summaries/{source.name}"
            await self.storage.write_bytes(destination, await asyncio.to_thread(source.read_bytes))
            await self.storage.remove(str(source.relative_to(self.storage.root)))

    async def store_upload(self, system: System, document_id: str, filename: str,
                           data: bytes, generated_markdown: str) -> str:
        key = self.workspace_relative(system)
        safe_name = _slug(Path(filename).stem, document_id) + Path(filename).suffix.lower()
        relative = f"{key}/uploads/{document_id}--{safe_name}"
        await self.storage.write_bytes(relative, data)
        await self.storage.write_text(
            f"{key}/generated/{document_id}--{_slug(Path(filename).stem, document_id)}.md",
            generated_markdown,
        )
        return f"workspace://{relative.replace(chr(92), '/')}"

    def resolve_uri(self, uri: str) -> Path:
        if not uri.startswith("workspace://"):
            raise ValueError("Unsupported workspace URI")
        return self.storage.resolve(uri.removeprefix("workspace://"))

    async def remove_document_files(self, document: KnowledgeDocument) -> None:
        if document.source_uri.startswith("workspace://"):
            await self.storage.remove(document.source_uri.removeprefix("workspace://"))
        system = await self.session.get(System, document.system_id)
        if system:
            key = self.workspace_relative(system)
            for directory in ("docs", "runbooks", "generated"):
                path = self.storage.resolve(f"{key}/{directory}")
                for candidate in path.glob(f"*{document.id}*"):
                    await self.storage.remove(str(candidate.relative_to(self.storage.root)))

    async def append_ai_memory(self, system_id: str, session_id: str,
                               payload: dict[str, Any]) -> str | None:
        system = await self.session.get(System, system_id)
        if system is None:
            return None
        key = self.workspace_relative(system)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        safe_payload = _redact_memory(payload)
        content = {
            "timestamp": datetime.now(UTC).isoformat(), "session_id": session_id, **safe_payload,
        }
        category = str(safe_payload.get("category", "summaries"))
        if category not in {"daily", "incidents", "operations", "summaries", "decisions"}:
            category = "summaries"
        relative = f"{key}/memory/{category}/{timestamp}--{uuid4().hex[:8]}.json"
        await self.storage.write_text(
            relative,
            json.dumps(content, ensure_ascii=False, indent=2, default=str),
        )
        if category == "summaries":
            history = ["# AI Session Event", "", f"- Timestamp: {content['timestamp']}",
                       f"- Session: `{session_id}`", f"- Result: {safe_payload.get('result', 'unknown')}", "",
                       "## Request", "", str(safe_payload.get("request", "")), "", "## Steps and decisions", ""]
            for event in safe_payload.get("tool_events", []):
                history.append(
                    f"- `{event.get('tool', 'unknown')}`: decision={event.get('decision', 'unknown')}"
                )
            history.extend(["", "## Final result", "", str(safe_payload.get("answer", "")), "",
                            "## Errors", "", json.dumps(safe_payload.get("errors", []), ensure_ascii=False)])
            await self.storage.write_text(
                f"{key}/history/{timestamp}--{session_id}.md", "\n".join(history))
        return relative

    async def append_conversation(self, system_id: str, session_id: str,
                                  payload: dict[str, Any]) -> str | None:
        system = await self.session.get(System, system_id)
        if system is None:
            return None
        key = self.workspace_relative(system)
        now = datetime.now(UTC)
        relative = f"{key}/conversations/{now:%Y-%m}/{session_id}.jsonl"
        path = self.storage.resolve(relative)
        safe = _redact_memory({"timestamp": now.isoformat(), **payload})
        existing = await asyncio.to_thread(path.read_text, encoding="utf-8") if path.is_file() else ""
        await self.storage.write_text(
            relative, existing + json.dumps(safe, ensure_ascii=False, default=str) + "\n"
        )
        await self.storage.write_text(
            f"{key}/summaries/conversation--{session_id}.md",
            f"# Conversation {session_id}\n\nLast activity: `{now.isoformat()}`\n\n"
            f"Latest request: {safe.get('user_message', '')}\n\n"
            f"Latest result: {safe.get('ai_response', '')}\n",
        )
        return relative

    async def clear_generated(self, system: System) -> None:
        key = self.workspace_relative(system)
        for directory in ("generated", "context"):
            await self.storage.remove(f"{key}/{directory}", recursive=True)

    async def clear_memory(self, system: System) -> None:
        key = self.workspace_relative(system)
        await self.storage.remove(f"{key}/memory", recursive=True)
        await self.storage.remove(f"{key}/history", recursive=True)

    async def clear_conversations(self, system: System) -> None:
        key = self.workspace_relative(system)
        await self.storage.remove(f"{key}/conversations", recursive=True)
        await self.storage.remove(f"{key}/summaries", recursive=True)

    async def remove_system(self, code: str) -> None:
        self.validate_system_code(code)
        await self.storage.remove(code, recursive=True)
