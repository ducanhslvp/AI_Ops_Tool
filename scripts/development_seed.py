import logging
import os
from pathlib import Path
import secrets
import sys
from datetime import UTC, datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import AsyncSessionFactory  # noqa: E402
from app.domain.models import (  # noqa: E402
    AiMessage,
    AiProviderConfiguration,
    AiSession,
    Alert,
    AuditLog,
    Credential,
    DiscoverySchedule,
    Environment,
    KnowledgeDocument,
    NotificationChannel,
    Permission,
    PlatformSetting,
    Plugin,
    PolicyRule,
    Report,
    ReportTemplate,
    Role,
    Server,
    SshGatewayProfile,
    System,
    User,
)
from app.services.audit_service import AuditService  # noqa: E402
from app.services.secret_manager import LocalAesSecretManager  # noqa: E402

logger = logging.getLogger("development_seed")

PERMISSIONS = [
    "*", "inventory:read", "inventory:write", "tool:execute", "ai:chat",
    "policy:read", "policy:write", "approval:decide", "ai:policy_bypass", "audit:read",
    "audit:delete",
    "secret:read_metadata", "secret:write", "report:read", "report:write",
]


async def _one(session, model, field, value):
    return await session.scalar(select(model).where(field == value))


async def _security(session) -> dict[str, User]:
    permissions: dict[str, Permission] = {}
    for code in PERMISSIONS:
        item = await _one(session, Permission, Permission.code, code)
        if item is None:
            item = Permission(code=code, description=f"Allows {code}")
            session.add(item)
        permissions[code] = item
    await session.flush()
    role_specs = {
        "Admin": PERMISSIONS,
        "Operator": ["inventory:read", "inventory:write", "tool:execute", "ai:chat",
                     "policy:read", "approval:decide", "ai:policy_bypass",
                     "audit:read", "report:read",
                     "report:write"],
        "Viewer": ["inventory:read", "policy:read", "audit:read", "report:read"],
    }
    roles: dict[str, Role] = {}
    for name, codes in role_specs.items():
        role = await _one(session, Role, Role.name, name)
        if role is None:
            role = Role(name=name, description=f"{name} platform role")
            session.add(role)
        role.permissions = [permissions[code] for code in codes]
        roles[name] = role
    await session.flush()
    specs = [
        ("admin@aiops.example.com", "AIOps Admin", "Admin", "Admin@123456"),
        ("operator@aiops.example.com", "Operations Engineer", "Operator", "Operator@123456"),
        ("viewer@aiops.example.com", "Read Only Viewer", "Viewer", "Viewer@123456"),
    ]
    users: dict[str, User] = {}
    for email, full_name, role_name, default_password in specs:
        user = await _one(session, User, User.email, email)
        if user is None:
            password = os.getenv(f"AIOPS_SEED_{role_name.upper()}_PASSWORD", default_password)
            user = User(email=email, full_name=full_name,
                        password_hash=hash_password(password), role=roles[role_name])
            session.add(user)
        else:
            user.role = roles[role_name]
            user.is_active = True
        users[email] = user
    await session.flush()
    return users


async def _inventory(session) -> tuple[dict[str, System], list[Server]]:
    environments: dict[str, Environment] = {}
    for name, description, risk in [
        ("Development", "Local controlled development environment", 1),
        ("Production", "Policy validation target; never locally executed in production", 10),
    ]:
        item = await _one(session, Environment, Environment.name, name)
        if item is None:
            item = Environment(name=name, description=description, risk_weight=risk)
            session.add(item)
        environments[name] = item
    systems: dict[str, System] = {}
    for code, name, owner, criticality in [
        ("ERP", "Enterprise Resource Planning", "Core Applications", "critical"),
        ("CRM", "Customer Relationship Management", "Sales Operations", "high"),
    ]:
        item = await _one(session, System, System.code, code)
        if item is None:
            item = System(code=code, name=name, owner=owner, criticality=criticality,
                          description=f"Development validation landscape for {name}.")
            session.add(item)
        systems[code] = item
    await session.flush()
    credential = await _one(session, Credential, Credential.name, "local-simulation-reference")
    if credential is None:
        credential = Credential(
            name="local-simulation-reference", provider="local_aes256_gcm",
            encrypted_payload=LocalAesSecretManager().encrypt(
                {"username": "local-simulation", "token": secrets.token_urlsafe(32)}
            ),
            metadata_json={"scope": "development adapter reference", "non_network": True},
        )
        session.add(credential)
        await session.flush()
    specs = [
        ("ERP", "erp-linux-01", "127.10.0.11", "Ubuntu 24.04", "linux", "application", "healthy"),
        ("ERP", "erp-windows-01", "127.10.0.12", "Windows Server 2022", "windows", "iis", "healthy"),
        ("ERP", "erp-redis-01", "127.10.0.13", "Ubuntu 24.04", "database", "redis", "redis_down"),
        ("ERP", "erp-oracle-01", "127.10.0.14", "Oracle Linux 9", "database", "oracle", "oracle_slow"),
        ("CRM", "crm-kafka-01", "127.20.0.11", "Ubuntu 24.04", "linux", "kafka", "kafka_lag"),
        ("CRM", "crm-nginx-01", "127.20.0.12", "Ubuntu 24.04", "linux", "nginx", "nginx_down"),
    ]
    servers: list[Server] = []
    for code, hostname, ip, os_name, server_type, role, profile in specs:
        server = await session.scalar(select(Server).where(Server.hostname == hostname))
        if server is None:
            server = Server(
                system_id=systems[code].id, environment_id=environments["Development"].id,
                credential_id=credential.id, hostname=hostname, ip_address=ip, os=os_name,
                server_type=server_type, role=role,
                description=f"Local {role} target using reviewed simulation snapshots.",
                tags=[code.lower(), "development", role, f"profile:{profile}"],
                status="degraded" if profile != "healthy" else "online",
                ssh_config={"port": 22, "test_profile": profile},
            )
            session.add(server)
        servers.append(server)
    await session.flush()
    return systems, servers


async def _operational_data(session, systems: dict[str, System], servers: list[Server],
                            admin: User) -> None:
    policies = [
        ("Development read-only diagnostics", "allow", 10, "Development", None, "low"),
        ("Development read-only extended diagnostics", "allow", 15, "Development", None,
         "medium"),
        ("Production service restart approval", "approval_required", 20, "Production",
         "restart_service", "high"),
        ("Development service restart approval", "approval_required", 30, "Development",
         "restart_service", "high"),
    ]
    for name, effect, priority, environment, action, risk in policies:
        if await _one(session, PolicyRule, PolicyRule.name, name) is None:
            session.add(PolicyRule(name=name, effect=effect, priority=priority,
                                   environment=environment, action=action, risk_level=risk,
                                   description="Development policy validation rule", is_active=True))
    schedule_name = "Daily ERP infrastructure discovery"
    if await _one(session, DiscoverySchedule, DiscoverySchedule.name, schedule_name) is None:
        session.add(DiscoverySchedule(name=schedule_name, system_id=systems["ERP"].id,
                                      requested_by_user_id=admin.id,
                                      server_ids=[], interval_minutes=1440, incremental=True,
                                      include_system_services=False, enabled=True,
                                      next_run_at=datetime.now(UTC) + timedelta(days=1)))
    for code, title, body, nodes, edges in [
        ("ERP", "ERP operations runbook", "# ERP Recovery\n\nStart with disk, CPU and memory diagnostics. Redis and Oracle changes require approval.",
         [{"id": "ERP", "type": "system"}, {"id": "redis", "type": "database"},
          {"id": "oracle", "type": "database"}],
         [{"source": "ERP", "target": "redis"}, {"source": "ERP", "target": "oracle"}]),
        ("CRM", "CRM edge and messaging runbook", "# CRM Recovery\n\nValidate Kafka lag and Nginx configuration before requesting changes.",
         [{"id": "CRM", "type": "system"}, {"id": "kafka", "type": "middleware"},
          {"id": "nginx", "type": "proxy"}],
         [{"source": "CRM", "target": "kafka"}, {"source": "CRM", "target": "nginx"}]),
    ]:
        if await _one(session, KnowledgeDocument, KnowledgeDocument.title, title) is None:
            session.add(KnowledgeDocument(system_id=systems[code].id, title=title,
                                          document_type="markdown", source_uri="seed://development",
                                          content_text=body, graph_nodes=nodes, graph_edges=edges))
    report_title = "Development environment baseline"
    if await _one(session, Report, Report.title, report_title) is None:
        session.add(Report(title=report_title, system_id=systems["ERP"].id, format="markdown",
                           content="# Development Baseline\n\nSix controlled targets are ready.",
                           generated_by_user_id=admin.id))
    for code, severity, title, server_index in [
        ("ERP", "critical", "Redis service unavailable", 2),
        ("CRM", "warning", "Kafka consumer lag increasing", 4),
        ("CRM", "critical", "Nginx configuration validation failed", 5),
    ]:
        if await _one(session, Alert, Alert.title, title) is None:
            session.add(Alert(system_id=systems[code].id, server_id=servers[server_index].id,
                              severity=severity, title=title,
                              description="Generated from the selected development test profile.",
                              status="open"))
    await session.flush()
    ai_session = await _one(session, AiSession, AiSession.title, "Development adapter readiness")
    if ai_session is None:
        ai_session = AiSession(user_id=admin.id, title="Development adapter readiness",
                               memory={"provider": "mock", "checked_tools": []})
        session.add(ai_session)
        await session.flush()
        session.add_all([
            AiMessage(session_id=ai_session.id, role="user",
                      content="Verify the local development adapter without infrastructure changes."),
            AiMessage(session_id=ai_session.id, role="assistant",
                      content="The environment is ready for policy-controlled snapshot diagnostics.",
                      tool_events=[], confidence={"score": 0.95, "reason": "Adapter guard validated",
                                                  "need_more_data": False}),
        ])
    for index, (server, tool) in enumerate(zip(servers, ["check_disk", "check_memory",
                                                         "check_service", "check_process",
                                                         "tail_log", "check_service"], strict=True)):
        prompt = f"Development readiness check for {server.hostname}"
        if await _one(session, AuditLog, AuditLog.prompt, prompt) is not None:
            continue
        await AuditService(session).record(
            user_id=admin.id, session_id=ai_session.id, server_id=server.id,
            prompt=prompt,
            reasoning_summary="Validated the registered read-only diagnostic path.",
            tool_name=tool, ssh_command=None, output="Development adapter target registered.",
            decision="allow", duration_ms=20 + index * 7, result="success",
        )


async def _configuration(session) -> None:
    items = [
        Plugin(name="Local Simulation", category="gateway", version="1.0.0", enabled=True,
               capabilities=["development_profiles", "reviewed_snapshots"]),
        Plugin(name="SSH", category="gateway", version="1.0.0", enabled=True,
               capabilities=["production_transport"]),
        Plugin(name="Host Discovery", category="discovery", version="1.0.0", enabled=True,
               capabilities=["linux", "windows", "filesystems", "network", "services"]),
        Plugin(name="Docker Discovery", category="discovery", version="1.0.0", enabled=True,
               capabilities=["containers", "networks", "compose"]),
        Plugin(name="Kubernetes Discovery", category="discovery", version="1.0.0", enabled=True,
               capabilities=["pods", "deployments", "services", "ingresses"]),
    ]
    for item in items:
        if await _one(session, Plugin, Plugin.name, item.name) is None:
            session.add(item)
    if await _one(session, ReportTemplate, ReportTemplate.name, "Development diagnostics") is None:
        session.add(ReportTemplate(name="Development diagnostics", format="markdown",
                                   description="Controlled local diagnostic report",
                                   template_body="# {system}\n\n{evidence}"))
    if await _one(session, SshGatewayProfile, SshGatewayProfile.name, "Development simulation") is None:
        session.add(SshGatewayProfile(name="Development simulation", is_active=True,
                                      description="Reviewed snapshot transport; no host command execution",
                                      config={"transport": "local_simulation", "output_limit_bytes": 1048576}))
    if await _one(session, AiProviderConfiguration, AiProviderConfiguration.name, "Local test AI") is None:
        session.add(AiProviderConfiguration(name="Local test AI", provider_type="mock",
                                            model="mock-operations-v1", config={"latency_ms": 5},
                                            enabled=True, is_active=True))
    if await _one(session, NotificationChannel, NotificationChannel.name, "Development in-app") is None:
        session.add(NotificationChannel(name="Development in-app", channel_type="in_app",
                                        config={"severity_min": "info"}, enabled=True))
    if await session.scalar(select(PlatformSetting).where(PlatformSetting.scope == "development",
                                                           PlatformSetting.key == "test_adapter")) is None:
        session.add(PlatformSetting(scope="development", key="test_adapter",
                                    value={"profile_selection": True, "arbitrary_shell": False},
                                    description="Local adapter feature state"))


async def seed_development_data() -> None:
    settings = get_settings()
    if not settings.test_features_enabled:
        raise RuntimeError("Development seed is disabled outside development/testing")
    async with AsyncSessionFactory() as session:
        users = await _security(session)
        systems, servers = await _inventory(session)
        await _operational_data(session, systems, servers, users["admin@aiops.example.com"])
        await _configuration(session)
        await session.commit()
    logger.info("Development seed reconciled: 3 users, 2 systems, 6 controlled targets")
