from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select

from app.api.dependencies import DbSession, require_permission
from app.domain.models import (
    AiMessage, AiProviderConfiguration, AiSession, Alert, AuditLog, Environment,
    KnowledgeDocument, Plugin, Server, SshGatewayProfile, System, User,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard(
    session: DbSession,
    _: User = Depends(require_permission("inventory:read")),
) -> dict:
    system_count = await session.scalar(select(func.count(System.id))) or 0
    server_count = await session.scalar(select(func.count(Server.id))) or 0
    online_count = await session.scalar(select(func.count(Server.id)).where(
        Server.status == "online")) or 0
    degraded_count = await session.scalar(select(func.count(Server.id)).where(
        Server.status == "degraded")) or 0
    offline_count = await session.scalar(select(func.count(Server.id)).where(
        Server.status == "offline")) or 0
    open_alerts = await session.scalar(select(func.count(Alert.id)).where(
        Alert.status == "open")) or 0
    critical_alerts = await session.scalar(select(func.count(Alert.id)).where(
        Alert.status == "open", Alert.severity == "critical")) or 0
    warning_alerts = await session.scalar(select(func.count(Alert.id)).where(
        Alert.status == "open", Alert.severity == "warning")) or 0
    ai_messages = await session.scalar(select(func.count(AiMessage.id))) or 0
    knowledge_count = await session.scalar(select(func.count(KnowledgeDocument.id))) or 0
    enabled_plugins = await session.scalar(select(func.count(Plugin.id)).where(
        Plugin.enabled.is_(True))) or 0
    total_plugins = await session.scalar(select(func.count(Plugin.id))) or 0
    active_providers = await session.scalar(select(func.count(AiProviderConfiguration.id)).where(
        AiProviderConfiguration.enabled.is_(True),
        AiProviderConfiguration.is_active.is_(True))) or 0
    active_gateways = await session.scalar(select(func.count(SshGatewayProfile.id)).where(
        SshGatewayProfile.is_active.is_(True))) or 0
    health = round((online_count / server_count) * 100) if server_count else 100

    alerts = (await session.scalars(select(Alert).where(Alert.status == "open")
        .order_by(case((Alert.severity == "critical", 0), (Alert.severity == "warning", 1),
                       else_=2), Alert.created_at.desc()).limit(8))).all()
    recent_audit = (await session.scalars(select(AuditLog)
        .order_by(AuditLog.created_at.desc()).limit(8))).all()
    systems = (await session.execute(select(
        System,
        func.count(Server.id),
        func.sum(case((Server.status == "online", 1), else_=0)),
    ).outerjoin(Server, Server.system_id == System.id).group_by(System.id)
        .order_by(System.name))).all()
    documents = (await session.scalars(select(KnowledgeDocument).order_by(
        KnowledgeDocument.updated_at.desc()).limit(20))).all()

    since = datetime.now(UTC) - timedelta(days=7)
    trend_rows = (await session.execute(select(
        func.date(AuditLog.created_at).label("day"),
        func.count(AuditLog.id).label("operations"),
        func.sum(case((AuditLog.result == "failed", 1), else_=0)).label("failures"),
        func.avg(AuditLog.duration_ms).label("latency"),
    ).where(AuditLog.created_at >= since).group_by(func.date(AuditLog.created_at))
        .order_by(func.date(AuditLog.created_at)))).all()
    active_sessions = (await session.scalars(select(AiSession)
        .order_by(AiSession.updated_at.desc()).limit(6))).all()
    environments = (await session.execute(select(
        Environment.name,
        func.count(Server.id),
        func.sum(case((Server.status == "online", 1), else_=0)),
    ).outerjoin(Server, Server.environment_id == Environment.id)
        .group_by(Environment.id).order_by(Environment.risk_weight.desc()))).all()

    recommendations = []
    if critical_alerts:
        recommendations.append({
            "severity": "critical", "title": "Review critical alerts",
            "reason": f"{critical_alerts} critical alert(s) require operator triage.",
            "action_url": "/audit",
        })
    if offline_count:
        recommendations.append({
            "severity": "warning", "title": "Investigate offline servers",
            "reason": f"{offline_count} server(s) are currently unreachable.",
            "action_url": "/inventory",
        })
    if not active_providers:
        recommendations.append({
            "severity": "warning", "title": "Activate an AI provider",
            "reason": "No enabled AI provider is marked active.",
            "action_url": "/settings/appearance",
        })

    return {
        "metrics": {
            "system_health": health, "systems": system_count, "servers": server_count,
            "online_servers": online_count, "degraded_servers": degraded_count,
            "offline_servers": offline_count, "open_alerts": open_alerts,
            "critical_alerts": critical_alerts, "warning_alerts": warning_alerts,
            "ai_messages": ai_messages,
        },
        "components": {
            "ai_providers": active_providers, "enabled_plugins": enabled_plugins,
            "total_plugins": total_plugins, "ssh_gateways": active_gateways,
            "knowledge_documents": knowledge_count,
        },
        "environments": [{"name": name, "servers": count,
                          "online": online or 0,
                          "health": round(((online or 0) / count) * 100) if count else 100}
                         for name, count, online in environments],
        "recommendations": recommendations,
        "trend": [{"time": str(day), "operations": operations,
                   "failures": failures or 0, "latency_ms": round(latency or 0)}
                  for day, operations, failures, latency in trend_rows],
        "alerts": [{"id": item.id, "title": item.title, "severity": item.severity,
                    "server_id": item.server_id, "created_at": item.created_at}
                   for item in alerts],
        "recent_audit": [{"id": item.id, "tool": item.tool_name, "server_id": item.server_id,
                          "user_id": item.user_id, "decision": item.decision,
                          "created_at": item.created_at} for item in recent_audit],
        "systems": [{"id": item.id, "code": item.code, "name": item.name,
                     "owner": item.owner, "criticality": item.criticality,
                     "servers": count, "health": round(((online or 0) / count) * 100)
                     if count else 100} for item, count, online in systems],
        "graph": [{"system_id": item.system_id, "title": item.title,
                   "nodes": item.graph_nodes, "edges": item.graph_edges} for item in documents],
        "ai_activity": [{"id": item.id, "title": item.title,
                         "provider": (item.memory or {}).get("provider", "unknown"),
                         "updated_at": item.updated_at} for item in active_sessions],
    }
