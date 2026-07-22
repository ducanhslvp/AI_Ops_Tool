from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PolicyRule, Server, User
from app.domain.models.enums import PolicyDecision
from app.services.tool_registry import ToolDescriptorInternal


@dataclass(frozen=True)
class PolicyContext:
    user: User
    server: Server
    action: str
    tool: ToolDescriptorInternal
    requested_at: datetime


class PolicyEngine:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def evaluate(self, context: PolicyContext) -> PolicyDecision:
        result = await self.session.execute(
            select(PolicyRule)
            .where(PolicyRule.is_active.is_(True))
            .order_by(PolicyRule.priority.asc())
        )
        for rule in result.scalars().all():
            if self._matches(rule, context):
                return PolicyDecision(rule.effect)
        if context.tool.risk_level != "low":
            return PolicyDecision.approval_required
        return PolicyDecision.allow

    def _matches(self, rule: PolicyRule, context: PolicyContext) -> bool:
        user_role = context.user.role.name
        environment = context.server.environment.name
        checks = [
            rule.role is None or rule.role == user_role,
            rule.environment is None or rule.environment == environment,
            rule.server_type is None or rule.server_type == context.server.server_type,
            rule.action is None or rule.action == context.action,
            rule.risk_level is None or rule.risk_level == context.tool.risk_level,
            self._within_time_window(rule.time_window, context.requested_at),
        ]
        return all(checks)

    @staticmethod
    def _within_time_window(window: dict, requested_at: datetime) -> bool:
        if not window:
            return True
        if window.get("timezone", "UTC") != "UTC":
            return False
        days = window.get("days")
        if days is not None and requested_at.weekday() not in days:
            return False
        start = window.get("start")
        end = window.get("end")
        if not start or not end:
            return True
        try:
            start_minutes = int(start[:2]) * 60 + int(start[3:])
            end_minutes = int(end[:2]) * 60 + int(end[3:])
        except (TypeError, ValueError):
            return False
        current = requested_at.hour * 60 + requested_at.minute
        if start_minutes <= end_minutes:
            return start_minutes <= current <= end_minutes
        return current >= start_minutes or current <= end_minutes
