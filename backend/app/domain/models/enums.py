from enum import StrEnum


class EnvironmentName(StrEnum):
    development = "Development"
    testing = "Testing"
    uat = "UAT"
    staging = "Staging"
    production = "Production"


class ServerStatus(StrEnum):
    online = "online"
    degraded = "degraded"
    offline = "offline"
    maintenance = "maintenance"


class ServerType(StrEnum):
    linux = "linux"
    windows = "windows"
    database = "database"
    docker = "docker"
    kubernetes = "kubernetes"
    network = "network"


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class PolicyDecision(StrEnum):
    allow = "allow"
    deny = "deny"
    approval_required = "approval_required"


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    executed = "executed"


class AuditResult(StrEnum):
    success = "success"
    denied = "denied"
    approval_required = "approval_required"
    failed = "failed"
