import hashlib
import json
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import AiMemory, Server, System
from app.workspace.builder import WorkspaceBuilder


@dataclass(frozen=True)
class WorkspaceContext:
    content: str
    sources: tuple[str, ...]
    workspace_path: str | None
    revision: str | None = None
    bootstrap: bool = False


class WorkspaceContextBuilder:
    """Builds a compact recovery context; Codex reads source material from its workspace."""

    bootstrap_files = (
        "system_prompt.md", "README.md", "architecture.md", "servers.yaml", "policy.yaml",
        "tools.md",
    )

    def __init__(self, session: AsyncSession, workspace: WorkspaceBuilder | None = None) -> None:
        self.session = session
        self.workspace = workspace or WorkspaceBuilder(session)

    async def build(
        self, *, system_id: str | None, server_id: str | None, message: str, session_id: str,
        provider_session_id: str | None = None, include_full_memory: bool = False,
        force_workspace_reload: bool = False,
    ) -> WorkspaceContext:
        system = await self._system(system_id, server_id)
        if system is None:
            return WorkspaceContext(
                content=("No System is selected. Give general guidance only and request a System "
                         "before operational work. Never request or expose secrets."),
                sources=(), workspace_path=None,
            )

        root = self.workspace.workspace_path(system)
        if not root.is_dir():
            await self.workspace.sync_system(system.id)
        revision = self._revision(root)
        bootstrap = not provider_session_id or force_workspace_reload
        sections = [
            "SYSTEM SCOPE",
            f"System: {system.code} - {system.name}",
            f"Workspace revision: {revision}",
        ]
        targets = list((await self.session.scalars(
            select(Server).where(Server.system_id == system.id).order_by(Server.hostname)
        )).all())
        if server_id:
            selected = next((item for item in targets if item.id == server_id), None)
            if selected:
                sections.extend(["", "SELECTED OPERATION TARGET",
                                 f"{selected.id} | {selected.hostname} | "
                                 f"{selected.ip_address} | {selected.os}"])
        elif targets:
            sections.extend(["", "AVAILABLE OPERATION TARGETS",
                             "No server was preselected. Choose server_id for each "
                             "run_ssh_command call:"])
            sections.extend(
                f"- {item.id} | {item.hostname} | {item.ip_address} | {item.os} | {item.status}"
                for item in targets
            )
        sources: list[str] = []
        if bootstrap:
            present = [name for name in self.bootstrap_files if (root / name).is_file()]
            sections.extend([
                "",
                "WORKSPACE BOOTSTRAP",
                "The current working directory is the isolated System workspace. Read only the "
                "files needed for the current task. Start with: " + ", ".join(present) + ".",
                "Read relevant runbooks before proposing operational action. Do not scan or repeat "
                "the entire workspace, docs, knowledge, history, or memory tree.",
            ])
            sources.extend(present)
            runbook = self._relevant_runbook(root, message)
            if runbook:
                relative, excerpt = runbook
                sections.extend(["", f"RELEVANT RUNBOOK EXCERPT ({relative})", excerpt])
                sources.append(relative)

        memories = await self._memories(system.id, message, include_full_memory)
        if memories:
            sections.extend(["", "MEMORY SUMMARY"])
            memory_budget = 48_000 if include_full_memory else 2_500
            for item in memories:
                line = f"- [{item.category}] {item.topic}: {item.summary[:500]}"
                if len(line) > memory_budget:
                    break
                sections.append(line)
                memory_budget -= len(line)
                sources.append(item.file_path)
        elif bootstrap:
            for relative, summary in self._workspace_memory_fallback(root, include_full_memory):
                if "MEMORY SUMMARY" not in sections:
                    sections.extend(["", "MEMORY SUMMARY"])
                sections.append(f"- {summary}")
                sources.append(relative)

        sections.extend([
            "",
            "Use the persistent Codex thread and workspace as the primary context. Use backend tools "
            "for infrastructure evidence; never access credentials or connect to SSH directly.",
        ])
        content = "\n".join(sections)
        await self.workspace.storage.write_text(
            f"{self.workspace.workspace_relative(system)}/context/latest.json",
            json.dumps({"session_id": session_id, "sources": sources,
                        "context_size": len(content), "revision": revision,
                        "bootstrap": bootstrap}, indent=2),
        )
        return WorkspaceContext(content=content, sources=tuple(dict.fromkeys(sources)),
                                workspace_path=str(root), revision=revision,
                                bootstrap=bootstrap)

    async def _system(self, system_id: str | None, server_id: str | None) -> System | None:
        if server_id:
            server = await self.session.get(Server, server_id)
            if server:
                return await self.session.get(System, server.system_id)
        return await self.session.get(System, system_id) if system_id else None

    async def _memories(self, system_id: str, message: str,
                        include_full: bool) -> list[AiMemory]:
        limit = 5_000 if include_full else 3
        items = list((await self.session.scalars(
            select(AiMemory).where(AiMemory.system_id == system_id,
                                   AiMemory.archived_at.is_(None))
            .order_by(AiMemory.occurred_at.desc()).limit(100 if not include_full else limit)
        )).all())
        if include_full:
            return self._deduplicate_memories(items)[:limit]
        terms = set(re.findall(r"[a-z0-9_-]{3,}", message.casefold()))
        ignored = {"server", "system", "command", "tool", "task", "current", "check"}
        relevant_terms = terms - ignored
        scored = [(sum(term in f"{item.topic} {item.summary}".casefold()
                       for term in relevant_terms), item) for item in items]
        ranked = sorted(scored, key=lambda value: (
            -value[0], -value[1].occurred_at.timestamp(),
        ))
        relevant = [item for score, item in ranked if score > 0]
        if not relevant:
            relevant = [item for _, item in ranked[:1]]
        return self._deduplicate_memories(relevant)[:limit]

    @staticmethod
    def _deduplicate_memories(items: list[AiMemory]) -> list[AiMemory]:
        """Collapse legacy category copies of the same conversation summary."""
        unique: list[AiMemory] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            key = (" ".join(item.topic.casefold().split()),
                   " ".join(item.summary.casefold().split()))
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    @staticmethod
    def _revision(root) -> str:
        values = []
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file() and not path.is_symlink() and "context" not in path.parts:
                    stat = path.stat()
                    values.append(f"{path.relative_to(root).as_posix()}:{stat.st_size}:{stat.st_mtime_ns}")
        return hashlib.sha256("\n".join(values).encode()).hexdigest()[:16]

    @staticmethod
    def _relevant_runbook(root, message: str) -> tuple[str, str] | None:
        terms = set(re.findall(r"[a-z0-9_-]{3,}", message.casefold()))
        candidates = []
        for path in (root / "runbooks").glob("*.md"):
            text = path.read_text(encoding="utf-8", errors="replace")
            score = sum(term in f"{path.stem} {text}".casefold() for term in terms)
            candidates.append((score, path, text))
        if not candidates:
            return None
        _, path, text = max(candidates, key=lambda item: (item[0], item[1].name))
        return path.relative_to(root).as_posix(), text[:1200]

    @staticmethod
    def _workspace_memory_fallback(root, include_full: bool) -> list[tuple[str, str]]:
        limit = 20 if include_full else 4
        paths = sorted((root / "memory").glob("*/*.json"),
                       key=lambda path: path.stat().st_mtime_ns, reverse=True)[:limit]
        values = []
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            request = str(payload.get("request") or payload.get("topic") or "operation")[:300]
            answer = str(payload.get("answer") or payload.get("result") or "")[:700]
            values.append((path.relative_to(root).as_posix(), f"{request}: {answer}"))
        return values
