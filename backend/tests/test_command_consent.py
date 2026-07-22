from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.routes.ai import _completed_command_consent_result
from app.domain.models.enums import ApprovalStatus, AuditResult


@pytest.mark.asyncio
async def test_completed_command_consent_retry_returns_stored_result() -> None:
    session = AsyncMock()
    consent = SimpleNamespace(
        id="consent-1",
        status=ApprovalStatus.executed,
        server_id="server-1",
        plan={"execution_result": {"decision": "allow", "stdout": "ok"}},
    )

    result = await _completed_command_consent_result(session, consent)

    assert result == {"decision": "allow", "stdout": "ok", "idempotent": True}
    session.scalar.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_completed_command_consent_recovers_failed_gateway_result_from_audit() -> None:
    session = AsyncMock()
    session.scalar.return_value = SimpleNamespace(
        result=AuditResult.failed,
        output="Command is not registered for local simulation",
        exit_code=None,
    )
    consent = SimpleNamespace(
        id="consent-2",
        status=ApprovalStatus.executed,
        server_id="server-1",
        plan={
            "session_id": "session-1",
            "command": "df -hPT",
        },
    )

    result = await _completed_command_consent_result(session, consent)

    assert result["decision"] == "rejected"
    assert result["error"] == "Command is not registered for local simulation"
    assert result["recovered_from_audit"] is True
    assert result["idempotent"] is True
    assert consent.plan["execution_result"]["decision"] == "rejected"
    session.commit.assert_awaited_once()
