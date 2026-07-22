from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db_session
from app.domain.models import Permission, Role, User
from app.main import create_app


@pytest.mark.asyncio
async def test_admin_crud_exports_dashboard_and_viewer_rbac() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        admin_permission = Permission(code="*", description="All permissions")
        read_permission = Permission(code="inventory:read", description="Read inventory")
        report_permission = Permission(code="report:read", description="Read reports")
        admin_role = Role(name="Admin", permissions=[admin_permission])
        viewer_role = Role(name="Viewer", permissions=[read_permission, report_permission])
        session.add_all(
            [
                User(
                    email="admin@functional.example.com",
                    full_name="Admin",
                    password_hash=hash_password("Admin@123456"),
                    role=admin_role,
                ),
                User(
                    email="viewer@functional.example.com",
                    full_name="Viewer",
                    password_hash=hash_password("Viewer@123456"),
                    role=viewer_role,
                ),
            ]
        )
        await session.commit()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin_login = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@functional.example.com",
                "password": "Admin@123456",
                "remember": False,
            },
        )
        viewer_login = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "viewer@functional.example.com",
                "password": "Viewer@123456",
                "remember": False,
            },
        )
        assert admin_login.status_code == viewer_login.status_code == 200
        admin_headers = {
            "Authorization": f"Bearer {admin_login.json()['access_token']}"
        }
        viewer_headers = {
            "Authorization": f"Bearer {viewer_login.json()['access_token']}"
        }

        system = await client.post(
            "/api/v1/inventory/systems",
            headers=admin_headers,
            json={
                "name": "Payments",
                "code": "PAY",
                "owner": "Finance",
                "description": "Payment system",
                "criticality": "critical",
            },
        )
        assert system.status_code == 201
        system_id = system.json()["id"]
        denied = await client.post(
            "/api/v1/inventory/systems",
            headers=viewer_headers,
            json={"name": "Denied", "code": "NO"},
        )
        assert denied.status_code == 403

        environment = await client.post(
            "/api/v1/inventory/environments",
            headers=admin_headers,
            json={"name": "Production", "description": "Live", "risk_weight": 10},
        )
        assert environment.status_code == 201
        environment_id = environment.json()["id"]
        credential = await client.post(
            "/api/v1/inventory/credentials",
            headers=admin_headers,
            json={
                "name": "Payments shared SSH",
                "system_id": system_id,
                "secret_payload": {"username": "payops", "password": "S3cure-SSH-pass"},
                "metadata_json": {"purpose": "functional-test"},
            },
        )
        assert credential.status_code == 201
        credential_body = credential.json()
        assert credential_body["system_id"] == system_id
        assert credential_body["username"] == "payops"
        assert "password" not in credential.text
        assert "encrypted_payload" not in credential.text
        server_payload = {
            "system_id": system_id,
            "environment_id": environment_id,
            "credential_id": credential_body["id"],
            "hostname": "pay-api-01",
            "ip_address": "10.20.30.40",
            "os": "Ubuntu 24.04",
            "server_type": "linux",
            "role": "api",
            "description": "Primary API",
            "tags": ["payment", "production"],
            "ssh_config": {"port": 22},
        }
        server = await client.post(
            "/api/v1/inventory/servers", headers=admin_headers, json=server_payload
        )
        assert server.status_code == 201
        server_id = server.json()["id"]
        assert server.json()["credential_username"] == "payops"
        assert server.json()["credential_scope"] == "shared"
        assert "password" not in server.text
        invalid_secret_request = await client.post(
            "/api/v1/inventory/servers",
            headers=admin_headers,
            json={**server_payload, "ssh_username": "invalid", "ssh_password": "NeverEchoMe"},
        )
        assert invalid_secret_request.status_code == 422
        assert "NeverEchoMe" not in invalid_secret_request.text
        shared_server = await client.put(
            f"/api/v1/inventory/servers/{server_id}",
            headers=admin_headers,
            json=server_payload,
        )
        assert shared_server.status_code == 200
        assert shared_server.json()["credential_scope"] == "shared"
        searched = await client.get(
            "/api/v1/inventory/servers?q=pay-api", headers=viewer_headers
        )
        assert searched.status_code == 200 and len(searched.json()) == 1
        assert searched.headers["x-total-count"] == "1"
        server_detail = await client.get(
            f"/api/v1/inventory/servers/{server_id}", headers=viewer_headers
        )
        assert server_detail.status_code == 200
        assert "encrypted_payload" not in server_detail.text

        development_status = await client.get(
            "/api/v1/development/status", headers=viewer_headers
        )
        assert development_status.status_code == 200
        assert {profile["id"] for profile in development_status.json()["profiles"]} >= {
            "healthy",
            "disk_full",
        }
        selected_profile = await client.put(
            f"/api/v1/development/servers/{server_id}/profile",
            headers=admin_headers,
            json={"profile": "disk_full"},
        )
        assert selected_profile.status_code == 200
        diagnostic = await client.post(
            "/api/v1/tools/execute",
            headers=admin_headers,
            json={
                "server_id": server_id,
                "action": "check_disk",
                "arguments": {},
                "reason": "Validate the controlled development adapter",
            },
        )
        assert diagnostic.status_code == 200
        assert diagnostic.json()["decision"] == "allow"
        assert "100%" in diagnostic.json()["stdout"]
        assert diagnostic.json()["command_ref"]

        knowledge_payload = {
            "system_id": system_id,
            "title": "Payment runbook",
            "document_type": "markdown",
            "content_text": "# Payment recovery\nUse approved diagnostics.",
            "graph_nodes": [{"id": "PAY", "type": "system"}],
            "graph_edges": [],
        }
        knowledge = await client.post(
            "/api/v1/knowledge", headers=admin_headers, json=knowledge_payload
        )
        assert knowledge.status_code == 201
        knowledge_id = knowledge.json()["id"]
        preview = await client.get(
            f"/api/v1/knowledge/{knowledge_id}", headers=viewer_headers
        )
        download = await client.get(
            f"/api/v1/knowledge/{knowledge_id}/download", headers=viewer_headers
        )
        assert preview.status_code == 200
        assert download.status_code == 200 and "approved diagnostics" in download.text

        policy = await client.post(
            "/api/v1/policy/rules",
            headers=admin_headers,
            json={
                "name": "Production restart approval",
                "description": "Require a human decision",
                "effect": "approval_required",
                "priority": 10,
                "environment": "Production",
                "action": "restart_service",
                "risk_level": "high",
                "time_window": {},
                "is_active": True,
            },
        )
        assert policy.status_code == 201
        policy_id = policy.json()["id"]
        duplicate = await client.post(
            f"/api/v1/policy/rules/{policy_id}/duplicate", headers=admin_headers
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["is_active"] is False
        status_update = await client.patch(
            f"/api/v1/policy/rules/{policy_id}/status",
            headers=admin_headers,
            json={"is_active": False},
        )
        assert status_update.status_code == 200
        assert status_update.json()["is_active"] is False
        bulk_delete = await client.post(
            "/api/v1/policy/rules/actions/bulk-delete",
            headers=admin_headers,
            json={"ids": [duplicate.json()["id"]]},
        )
        assert bulk_delete.status_code == 200
        assert bulk_delete.json() == {"deleted": 1}

        provider = await client.post(
            "/api/v1/admin/ai-providers",
            headers=admin_headers,
            json={"name": "connection-test", "provider_type": "mock",
                  "model": "mock-operations-v1", "config": {}, "enabled": True,
                  "is_active": False},
        )
        assert provider.status_code == 201
        provider_id = provider.json()["id"]
        provider_health = await client.post(
            f"/api/v1/admin/ai-providers/{provider_id}/test-connection",
            headers=admin_headers,
        )
        assert provider_health.status_code == 200
        assert provider_health.json()["status"] == "ready"

        setting = await client.post(
            "/api/v1/admin/settings",
            headers=admin_headers,
            json={
                "scope": "observability",
                "key": "retention",
                "value": {"audit_days": 365},
                "description": "Retention policy",
            },
        )
        assert setting.status_code == 201
        setting_id = setting.json()["id"]

        report = await client.post(
            "/api/v1/reports",
            headers=admin_headers,
            json={"title": "Payment health", "system_id": system_id,
                  "server_id": server_id, "format": "pdf"},
        )
        assert report.status_code == 201
        assert report.json()["server_id"] == server_id
        report_id = report.json()["id"]
        report_download = await client.get(
            f"/api/v1/reports/{report_id}/download", headers=viewer_headers
        )
        assert report_download.status_code == 200
        assert report_download.headers["content-type"].startswith("application/pdf")
        assert report_download.content.startswith(b"%PDF")

        global_search = await client.get(
            "/api/v1/search?q=Payment", headers=viewer_headers
        )
        assert global_search.status_code == 200
        result_kinds = {item["kind"] for item in global_search.json()["items"]}
        assert {"system", "knowledge", "report"} <= result_kinds

        dashboard = await client.get("/api/v1/dashboard", headers=viewer_headers)
        audit_export = await client.get("/api/v1/audit/export", headers=admin_headers)
        assert dashboard.status_code == 200
        assert dashboard.json()["metrics"]["systems"] == 1
        assert dashboard.json()["components"]["knowledge_documents"] == 1
        assert audit_export.status_code == 200
        assert audit_export.headers["content-type"].startswith("text/csv")

        for path in [
            f"/api/v1/reports/{report_id}",
            f"/api/v1/knowledge/{knowledge_id}",
            f"/api/v1/policy/rules/{policy_id}",
            f"/api/v1/admin/settings/{setting_id}",
            f"/api/v1/admin/ai-providers/{provider_id}",
            f"/api/v1/inventory/servers/{server_id}",
            f"/api/v1/inventory/systems/{system_id}",
            f"/api/v1/inventory/environments/{environment_id}",
        ]:
            response = await client.delete(path, headers=admin_headers)
            assert response.status_code == 204

    await engine.dispose()
