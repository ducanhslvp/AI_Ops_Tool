from fastapi import APIRouter, Depends, Query
from sqlalchemy import literal, select

from app.api.dependencies import DbSession, require_permission
from app.domain.models import (
    AiSession,
    KnowledgeDocument,
    Plugin,
    PolicyRule,
    Report,
    Server,
    System,
    User,
)

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def global_search(
    session: DbSession,
    user: User = Depends(require_permission("inventory:read")),
    q: str = Query(min_length=2, max_length=100),
    limit: int = Query(5, ge=1, le=10),
) -> dict:
    pattern = f"%{q.strip()}%"
    statements = [
        select(
            literal("system").label("kind"),
            System.id.label("id"),
            System.name.label("title"),
            System.code.label("subtitle"),
            literal("/inventory").label("url"),
        ).where(System.name.ilike(pattern) | System.code.ilike(pattern)).limit(limit),
        select(
            literal("server").label("kind"),
            Server.id.label("id"),
            Server.hostname.label("title"),
            Server.ip_address.label("subtitle"),
            (literal("/inventory/servers/") + Server.id).label("url"),
        ).where(Server.hostname.ilike(pattern) | Server.ip_address.ilike(pattern)).limit(limit),
        select(
            literal("knowledge").label("kind"),
            KnowledgeDocument.id.label("id"),
            KnowledgeDocument.title.label("title"),
            KnowledgeDocument.document_type.label("subtitle"),
            literal("/knowledge").label("url"),
        ).where(
            KnowledgeDocument.title.ilike(pattern)
            | KnowledgeDocument.content_text.ilike(pattern)
        ).limit(limit),
        select(
            literal("report").label("kind"),
            Report.id.label("id"),
            Report.title.label("title"),
            Report.format.label("subtitle"),
            literal("/reports").label("url"),
        ).where(Report.title.ilike(pattern)).limit(limit),
        select(
            literal("policy").label("kind"),
            PolicyRule.id.label("id"),
            PolicyRule.name.label("title"),
            PolicyRule.effect.label("subtitle"),
            literal("/policy").label("url"),
        ).where(PolicyRule.name.ilike(pattern)).limit(limit),
        select(
            literal("plugin").label("kind"),
            Plugin.id.label("id"),
            Plugin.name.label("title"),
            Plugin.category.label("subtitle"),
            literal("/settings/appearance").label("url"),
        ).where(Plugin.name.ilike(pattern)).limit(limit),
        select(
            literal("ai_session").label("kind"),
            AiSession.id.label("id"),
            AiSession.title.label("title"),
            literal("AI session").label("subtitle"),
            literal("/chats").label("url"),
        ).where(AiSession.user_id == user.id, AiSession.title.ilike(pattern)).limit(limit),
    ]
    permissions = {permission.code for permission in user.role.permissions}
    if "*" in permissions:
        statements.append(
            select(
                literal("user").label("kind"),
                User.id.label("id"),
                User.full_name.label("title"),
                User.email.label("subtitle"),
                literal("/users").label("url"),
            ).where(User.full_name.ilike(pattern) | User.email.ilike(pattern)).limit(limit)
        )
    items: list[dict] = []
    for statement in statements:
        rows = (await session.execute(statement)).mappings().all()
        items.extend(dict(row) for row in rows)
    return {"query": q, "items": items, "total": len(items)}
