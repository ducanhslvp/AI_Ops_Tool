from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.domain.models import AiSession, Environment, KnowledgeDocument, PolicyRule, Server, System
from app.services.memory_service import MemoryService
from app.workspace import LocalWorkspaceStorage, WorkspaceBuilder, WorkspaceContextBuilder


@pytest.fixture
async def workspace_session(isolated_workspace_root):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        system = System(name="Payments", code="PAY", owner="Finance",
                        description="Payment processing", criticality="critical")
        environment = Environment(name="Production", description="Production", risk_weight=10)
        session.add_all([system, environment])
        await session.flush()
        server = Server(
            system_id=system.id, environment_id=environment.id, credential_id=None,
            hostname="pay-app-01", ip_address="10.0.0.10", os="Ubuntu 24.04",
            server_type="linux", role="nginx docker", description="Payment API",
            tags=["redis", "kafka"], status="online",
            ssh_config={"port": 22, "known_hosts": "strict"},
        )
        runbook = KnowledgeDocument(
            system_id=system.id, title="Restart payment API", document_type="runbook",
            source_uri="", content_text="# Restart\nUse restart_service after approval.",
            graph_nodes=[], graph_edges=[],
        )
        policy = PolicyRule(
            name="Production restart approval", description="", effect="approval_required",
            priority=10, environment="Production", action="restart_service",
            time_window={}, is_active=True,
        )
        session.add_all([server, runbook, policy])
        await session.commit()
        yield session, system
    await engine.dispose()


@pytest.mark.asyncio
async def test_workspace_projection_is_complete_and_secret_free(
    workspace_session, isolated_workspace_root
) -> None:
    session, system = workspace_session
    storage = LocalWorkspaceStorage(isolated_workspace_root)
    builder = WorkspaceBuilder(session, storage)
    root = await builder.sync_system(system.id)
    expected = {
        "README.md", "servers.yaml", "policy.yaml", "tools.md", "system_prompt.md",
        "inventory.md", "architecture.md", "topology.md", "dependencies.md", "services.md",
    }
    assert expected <= {item.name for item in root.iterdir()}
    servers_yaml = (root / "servers.yaml").read_text(encoding="utf-8").lower()
    assert "credential" not in servers_yaml
    assert "private_key" not in servers_yaml
    assert "password" not in servers_yaml
    assert list((root / "runbooks").glob("*restart-payment-api*.md"))
    assert (root / "skills" / "linux.md").is_file()
    assert (root / "skills" / "docker.md").is_file(), [
        path.name for path in (root / "skills").glob("*.md")
    ]


@pytest.mark.asyncio
async def test_context_upload_and_memory_use_workspace_only(
    workspace_session, isolated_workspace_root
) -> None:
    session, system = workspace_session
    storage = LocalWorkspaceStorage(isolated_workspace_root)
    builder = WorkspaceBuilder(session, storage)
    await builder.sync_system(system.id)
    uri = await builder.store_upload(
        system, "doc-1", "Architecture.pdf", b"original-pdf",
        "# Extracted architecture\nPayment API depends on Redis.",
    )
    assert uri.startswith("workspace://PAY/uploads/")
    assert builder.resolve_uri(uri).read_bytes() == b"original-pdf"
    await builder.append_ai_memory(system.id, "session-1", {
        "request": "check payment", "tool_events": [], "answer": "healthy",
        "errors": [], "result": "success",
    })
    context = await WorkspaceContextBuilder(session, builder).build(
        system_id=system.id, server_id=None, message="restart payment API",
        session_id="session-1",
    )
    assert "Use restart_service after approval" in context.content
    assert "check payment" in context.content
    assert "AVAILABLE OPERATION TARGETS" in context.content
    assert "pay-app-01" in context.content
    assert context.workspace_path == str(Path(isolated_workspace_root) / "PAY")
    assert len(context.content) <= 80_000 + 5_000


@pytest.mark.asyncio
async def test_categorized_memory_archive_and_independent_resets(
    workspace_session, isolated_workspace_root
) -> None:
    session, system = workspace_session
    storage = LocalWorkspaceStorage(isolated_workspace_root)
    builder = WorkspaceBuilder(session, storage)
    await builder.sync_system(system.id)
    ai_session = AiSession(user_id="test-user", system_id=system.id, title="Incident",
                           memory={}, status="idle")
    session.add(ai_session)
    await session.flush()
    service = MemoryService(session, builder)
    records = await service.record(
        system_id=system.id, session_id=ai_session.id, request="Redis is down",
        answer="Redis is unavailable.",
        tool_events=[{"tool": "check_service", "decision": "allow", "error": "failed"}],
        confidence={"score": 0.9}, provider="mock", context_sources=["runbooks/redis.md"],
    )
    assert len(records) == 1
    assert records[0].category == "summaries"
    assert records[0].details["classifications"] == ["operation", "incident", "decision"]
    assert all(storage.resolve(item.file_path).is_file() for item in records)
    assert await service.archive(system) == 1
    active, active_total = await service.list(
        system.id, query=None, category=None, archived=False, offset=0, limit=50
    )
    archived, archived_total = await service.list(
        system.id, query="Redis", category=None, archived=True, offset=0, limit=50
    )
    assert active == [] and active_total == 0
    assert len(archived) == archived_total == 1
    assert await service.reset_conversations(system) == 1
    remaining, total = await service.list(
        system.id, query=None, category=None, archived=True, offset=0, limit=50
    )
    assert total == 1 and all(item.session_id is None for item in remaining)
