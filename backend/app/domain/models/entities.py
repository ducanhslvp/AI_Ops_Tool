from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy import JSON as SAJSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class Role(Base, IdMixin, TimestampMixin):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", back_populates="roles", lazy="selectin"
    )


class Permission(Base, IdMixin, TimestampMixin):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    roles: Mapped[list[Role]] = relationship(
        secondary="role_permissions", back_populates="permissions", lazy="selectin"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[str] = mapped_column(ForeignKey("permissions.id"), primary_key=True)


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"))
    role: Mapped[Role] = relationship(lazy="selectin")


class RefreshToken(Base, IdMixin, TimestampMixin):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)


class Environment(Base, IdMixin, TimestampMixin):
    __tablename__ = "environments"

    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    risk_weight: Mapped[int] = mapped_column(Integer, default=1)


class System(Base, IdMixin, TimestampMixin):
    __tablename__ = "systems"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    owner: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    criticality: Mapped[str] = mapped_column(String(40), default="medium")
    default_credential_id: Mapped[str | None] = mapped_column(
        ForeignKey("credentials.id"), nullable=True, index=True
    )


class Credential(Base, IdMixin, TimestampMixin):
    __tablename__ = "credentials"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    system_id: Mapped[str | None] = mapped_column(
        ForeignKey("systems.id"), nullable=True, index=True
    )
    username: Mapped[str] = mapped_column(String(120), default="")
    provider: Mapped[str] = mapped_column(String(80), default="local_aes256_gcm")
    encrypted_payload: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(SAJSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Server(Base, IdMixin, TimestampMixin):
    __tablename__ = "servers"
    __table_args__ = (UniqueConstraint("system_id", "hostname", name="uq_server_system_hostname"),)

    system_id: Mapped[str] = mapped_column(ForeignKey("systems.id"), index=True)
    environment_id: Mapped[str] = mapped_column(ForeignKey("environments.id"), index=True)
    credential_id: Mapped[str | None] = mapped_column(ForeignKey("credentials.id"), nullable=True)
    hostname: Mapped[str] = mapped_column(String(120), index=True)
    ip_address: Mapped[str] = mapped_column(String(80), index=True)
    os: Mapped[str] = mapped_column(String(80))
    server_type: Mapped[str] = mapped_column(String(40), index=True)
    role: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(SAJSON, default=list)
    status: Mapped[str] = mapped_column(String(40), default="online", index=True)
    ssh_config: Mapped[dict] = mapped_column(SAJSON, default=dict)

    system: Mapped[System] = relationship(lazy="selectin")
    environment: Mapped[Environment] = relationship(lazy="selectin")
    credential: Mapped[Credential | None] = relationship(lazy="selectin")

    @property
    def credential_username(self) -> str:
        return self.credential.username if self.credential else ""

    @property
    def credential_scope(self) -> str:
        if self.credential is None:
            return "none"
        return str((self.credential.metadata_json or {}).get("scope", "shared"))


class PolicyRule(Base, IdMixin, TimestampMixin):
    __tablename__ = "policy_rules"

    name: Mapped[str] = mapped_column(String(160), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    effect: Mapped[str] = mapped_column(String(40), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(80), nullable=True)
    server_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action: Mapped[str | None] = mapped_column(String(120), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(40), nullable=True)
    time_window: Mapped[dict] = mapped_column(SAJSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ToolConfiguration(Base, IdMixin, TimestampMixin):
    __tablename__ = "tool_configurations"

    tool_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(40), index=True)
    target_types: Mapped[list[str]] = mapped_column(SAJSON, default=list)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class ApprovalRequest(Base, IdMixin, TimestampMixin):
    __tablename__ = "approval_requests"

    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    server_id: Mapped[str | None] = mapped_column(ForeignKey("servers.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    reason: Mapped[str] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(Text, default="")
    plan: Mapped[dict] = mapped_column(SAJSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    decided_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base, IdMixin):
    __tablename__ = "audit_logs"

    sequence_number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    server_id: Mapped[str | None] = mapped_column(ForeignKey("servers.id"), nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    context_sources: Mapped[list[str]] = mapped_column(SAJSON, default=list)
    tool_events: Mapped[list[dict]] = mapped_column(SAJSON, default=list)
    reasoning_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    ssh_command: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approval_used: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[str] = mapped_column(String(40), index=True)
    integrity_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    integrity_version: Mapped[int] = mapped_column(Integer, default=2)


class KnowledgeDocument(Base, IdMixin, TimestampMixin):
    __tablename__ = "knowledge_documents"

    system_id: Mapped[str] = mapped_column(ForeignKey("systems.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    document_type: Mapped[str] = mapped_column(String(80))
    source_uri: Mapped[str] = mapped_column(String(500), default="")
    content_text: Mapped[str] = mapped_column(Text, default="")
    graph_nodes: Mapped[list[dict]] = mapped_column(SAJSON, default=list)
    graph_edges: Mapped[list[dict]] = mapped_column(SAJSON, default=list)


class Plugin(Base, IdMixin, TimestampMixin):
    __tablename__ = "plugins"

    name: Mapped[str] = mapped_column(String(120), unique=True)
    category: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(40), default="1.0.0")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    capabilities: Mapped[list[str]] = mapped_column(SAJSON, default=list)
    config_schema: Mapped[dict] = mapped_column(SAJSON, default=dict)


class Report(Base, IdMixin, TimestampMixin):
    __tablename__ = "reports"

    system_id: Mapped[str | None] = mapped_column(ForeignKey("systems.id"), nullable=True)
    server_id: Mapped[str | None] = mapped_column(ForeignKey("servers.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    format: Mapped[str] = mapped_column(String(40), default="markdown")
    content: Mapped[str] = mapped_column(Text)
    generated_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class ReportTemplate(Base, IdMixin, TimestampMixin):
    __tablename__ = "report_templates"

    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    format: Mapped[str] = mapped_column(String(40), default="markdown")
    template_body: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PlatformSetting(Base, IdMixin, TimestampMixin):
    __tablename__ = "platform_settings"
    __table_args__ = (UniqueConstraint("scope", "key", name="uq_platform_setting_scope_key"),)

    scope: Mapped[str] = mapped_column(String(80), default="platform", index=True)
    key: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[dict] = mapped_column(SAJSON, default=dict)
    description: Mapped[str] = mapped_column(String(255), default="")


class NotificationChannel(Base, IdMixin, TimestampMixin):
    __tablename__ = "notification_channels"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    channel_type: Mapped[str] = mapped_column(String(40), index=True)
    config: Mapped[dict] = mapped_column(SAJSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SshGatewayProfile(Base, IdMixin, TimestampMixin):
    __tablename__ = "ssh_gateway_profiles"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    config: Mapped[dict] = mapped_column(SAJSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AiProviderConfiguration(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_provider_configurations"

    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    provider_type: Mapped[str] = mapped_column(String(40), index=True)
    model: Mapped[str] = mapped_column(String(160))
    config: Mapped[dict] = mapped_column(SAJSON, default=dict)
    secret_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    exclusive_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    health_status: Mapped[str] = mapped_column(String(40), default="unknown")
    health_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Alert(Base, IdMixin, TimestampMixin):
    __tablename__ = "alerts"

    system_id: Mapped[str] = mapped_column(ForeignKey("systems.id"), index=True)
    server_id: Mapped[str | None] = mapped_column(ForeignKey("servers.id"), nullable=True)
    severity: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)


class AiSession(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    system_id: Mapped[str | None] = mapped_column(ForeignKey("systems.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    memory: Mapped[dict] = mapped_column(SAJSON, default=dict)
    provider_session_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="idle", index=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context_size: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reasoning_effort: Mapped[str] = mapped_column(String(20), default="medium")
    include_full_memory: Mapped[bool] = mapped_column(Boolean, default=False)
    accept_all_commands: Mapped[bool] = mapped_column(Boolean, default=False)
    bypass_policy: Mapped[bool] = mapped_column(Boolean, default=False)


class AiMessage(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_messages"

    session_id: Mapped[str] = mapped_column(ForeignKey("ai_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    tool_events: Mapped[list[dict]] = mapped_column(SAJSON, default=list)
    confidence: Mapped[dict] = mapped_column(SAJSON, default=dict)


class AiCommandApproval(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_command_approvals"
    __table_args__ = (UniqueConstraint(
        "user_id", "system_id", "server_id", "command_hash",
        name="uq_ai_command_approval_scope",
    ),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    system_id: Mapped[str | None] = mapped_column(
        ForeignKey("systems.id"), nullable=True, index=True
    )
    server_id: Mapped[str | None] = mapped_column(
        ForeignKey("servers.id"), nullable=True, index=True
    )
    command_hash: Mapped[str] = mapped_column(String(64), index=True)
    command: Mapped[str] = mapped_column(Text)
    effect: Mapped[str] = mapped_column(String(40), default="approval_required", index=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class AiMemory(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_memories"

    system_id: Mapped[str] = mapped_column(ForeignKey("systems.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("ai_sessions.id"), nullable=True,
                                                    index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    topic: Mapped[str] = mapped_column(String(200), index=True)
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(SAJSON, default=dict)
    source_type: Mapped[str] = mapped_column(String(40), default="conversation", index=True)
    source_refs: Mapped[list[str]] = mapped_column(SAJSON, default=list)
    file_path: Mapped[str] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True,
                                                         index=True)


class DiscoveryScan(Base, IdMixin, TimestampMixin):
    __tablename__ = "discovery_scans"

    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    system_id: Mapped[str | None] = mapped_column(ForeignKey("systems.id"), nullable=True,
                                                   index=True)
    baseline_scan_id: Mapped[str | None] = mapped_column(ForeignKey("discovery_scans.id"),
                                                          nullable=True)
    scope_type: Mapped[str] = mapped_column(String(40), index=True)
    server_ids: Mapped[list[str]] = mapped_column(SAJSON, default=list)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    options: Mapped[dict] = mapped_column(SAJSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
    nodes: Mapped[list[dict]] = mapped_column(SAJSON, default=list)
    edges: Mapped[list[dict]] = mapped_column(SAJSON, default=list)
    raw_evidence: Mapped[dict] = mapped_column(SAJSON, default=dict)
    change_summary: Mapped[dict] = mapped_column(SAJSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiscoverySchedule(Base, IdMixin, TimestampMixin):
    __tablename__ = "discovery_schedules"

    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    system_id: Mapped[str | None] = mapped_column(ForeignKey("systems.id"), nullable=True,
                                                   index=True)
    server_ids: Mapped[list[str]] = mapped_column(SAJSON, default=list)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    incremental: Mapped[bool] = mapped_column(Boolean, default=True)
    include_system_services: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True,
                                                          index=True)


@event.listens_for(AuditLog, "before_update")
@event.listens_for(AuditLog, "before_delete")
def prevent_audit_mutation(*_: object) -> None:
    raise ValueError("Audit records are append-only")
