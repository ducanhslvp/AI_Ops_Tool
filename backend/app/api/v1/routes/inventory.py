from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, or_, select

from app.api.dependencies import (
    CurrentUser, DbSession, get_secret_manager, get_ssh_gateway, require_permission,
)
from app.core.exceptions import AppError
from app.domain.models import Credential, Environment, KnowledgeDocument, Server, System, User
from app.schemas.inventory import (
    CredentialCreate, CredentialOut, CredentialUpdate, EnvironmentOut, EnvironmentWrite,
    ServerCreate, ServerOut, SystemCreate, SystemOut,
)
from app.schemas.common import PaginationDep, set_pagination_headers
from app.services.secret_manager import SecretManager
from app.services.ssh_gateway import SshGateway
from app.services.inventory_excel import read_rows, template_response
from app.workspace import WorkspaceBuilder

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _safe_import_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(map(str, error['loc']))}: {error['msg']}" for error in exc.errors()
        )[:300]
    if isinstance(exc, HTTPException):
        return str(exc.detail)[:300]
    if isinstance(exc, ValueError):
        return str(exc)[:300]
    return "The row conflicts with existing inventory data"


async def _get_or_404(session: DbSession, model: type, item_id: str):
    item = await session.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return item


@router.get("/systems", response_model=list[SystemOut])
async def list_systems(session: DbSession, _: CurrentUser, response: Response,
                       pagination: PaginationDep, q: str = "",
                       sort: str = Query("name"), direction: str = Query("asc")):
    statement = select(System)
    if q:
        statement = statement.where(or_(System.name.ilike(f"%{q}%"),
                                        System.code.ilike(f"%{q}%")))
    total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    set_pagination_headers(response, total or 0, pagination)
    column = {"name": System.name, "code": System.code,
              "criticality": System.criticality}.get(sort, System.name)
    order = column.desc() if direction == "desc" else column.asc()
    return list((await session.scalars(statement.order_by(order).offset(
        pagination.offset).limit(pagination.page_size))).all())


@router.get("/systems/import-template")
async def system_import_template(
    _: User = Depends(require_permission("inventory:write")),
):
    return template_response("systems")


@router.post("/systems/import")
async def import_systems(
    session: DbSession,
    file: UploadFile = File(...),
    _: User = Depends(require_permission("inventory:write")),
) -> dict:
    rows = read_rows(await file.read(5 * 1024 * 1024 + 1), "systems")
    created = updated = 0
    errors: list[dict] = []
    touched: list[str] = []
    for row_number, row in rows:
        try:
            payload = SystemCreate.model_validate({
                "code": str(row.get("code") or "").strip(),
                "name": str(row.get("name") or "").strip(),
                "owner": str(row.get("owner") or "").strip(),
                "description": str(row.get("description") or "").strip(),
                "criticality": str(row.get("criticality") or "medium").strip().lower(),
            })
            item = await session.scalar(select(System).where(System.code == payload.code))
            name_conflict = await session.scalar(select(System.id).where(
                System.name == payload.name,
                System.code != payload.code,
            ))
            if name_conflict:
                raise ValueError("System name is already used by another code")
            if item is None:
                item = System(**payload.model_dump())
                session.add(item)
                await session.flush()
                created += 1
            else:
                for key, value in payload.model_dump().items():
                    setattr(item, key, value)
                updated += 1
            touched.append(item.id)
        except Exception as exc:
            errors.append({"row": row_number, "error": _safe_import_error(exc)})
    workspace = WorkspaceBuilder(session)
    for system_id in set(touched):
        await workspace.sync_system(system_id)
    await session.commit()
    return {"created": created, "updated": updated, "failed": len(errors), "errors": errors}


@router.get("/systems/{item_id}")
async def get_system(
    item_id: str, session: DbSession,
    _: User = Depends(require_permission("inventory:read")),
) -> dict:
    system = await _get_or_404(session, System, item_id)
    servers = list((await session.scalars(
        select(Server).where(Server.system_id == item_id).order_by(Server.hostname)
    )).all())
    documents = list((await session.scalars(
        select(KnowledgeDocument).where(KnowledgeDocument.system_id == item_id)
        .order_by(KnowledgeDocument.updated_at.desc())
    )).all())
    return {
        "system": SystemOut.model_validate(system).model_dump(),
        "servers": [ServerOut.model_validate(item).model_dump() for item in servers],
        "knowledge": [{"id": item.id, "title": item.title,
                       "document_type": item.document_type,
                       "updated_at": item.updated_at} for item in documents],
    }


@router.post("/systems", response_model=SystemOut, status_code=201)
async def create_system(payload: SystemCreate, session: DbSession,
                        _: User = Depends(require_permission("inventory:write"))):
    if payload.default_credential_id:
        credential = await _get_or_404(session, Credential, payload.default_credential_id)
        if credential.system_id is not None:
            raise HTTPException(
                status_code=422,
                detail="A new System can use only a Global default credential",
            )
    item = System(**payload.model_dump())
    session.add(item)
    await session.flush()
    await WorkspaceBuilder(session).sync_system(item.id)
    await session.commit()
    await session.refresh(item)
    return item


@router.put("/systems/{item_id}", response_model=SystemOut)
async def update_system(item_id: str, payload: SystemCreate, session: DbSession,
                        _: User = Depends(require_permission("inventory:write"))):
    item = await _get_or_404(session, System, item_id)
    if payload.default_credential_id:
        credential = await _get_or_404(session, Credential, payload.default_credential_id)
        if credential.system_id not in {None, item.id}:
            raise HTTPException(
                status_code=422,
                detail="Default credential must be Global or belong to this System",
            )
    old_code = item.code
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    await session.flush()
    workspace = WorkspaceBuilder(session)
    await workspace.sync_system(item.id)
    if old_code != item.code:
        await workspace.remove_system(old_code)
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/systems/{item_id}", status_code=204)
async def delete_system(item_id: str, session: DbSession,
                        _: User = Depends(require_permission("inventory:write"))):
    item = await _get_or_404(session, System, item_id)
    code = item.code
    await session.delete(item)
    await session.commit()
    await WorkspaceBuilder(session).remove_system(code)
    return Response(status_code=204)


@router.get("/environments", response_model=list[EnvironmentOut])
async def list_environments(session: DbSession, _: CurrentUser, response: Response,
                            pagination: PaginationDep, q: str = ""):
    statement = select(Environment).order_by(Environment.risk_weight, Environment.name)
    if q:
        statement = statement.where(Environment.name.ilike(f"%{q}%"))
    total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    set_pagination_headers(response, total or 0, pagination)
    return list((await session.scalars(statement.offset(pagination.offset).limit(
        pagination.page_size))).all())


@router.post("/environments", response_model=EnvironmentOut, status_code=201)
async def create_environment(payload: EnvironmentWrite, session: DbSession,
                             _: User = Depends(require_permission("inventory:write"))):
    item = Environment(**payload.model_dump())
    session.add(item)
    await session.flush()
    await WorkspaceBuilder(session).sync_all()
    await session.commit()
    await session.refresh(item)
    return item


@router.put("/environments/{item_id}", response_model=EnvironmentOut)
async def update_environment(item_id: str, payload: EnvironmentWrite, session: DbSession,
                             _: User = Depends(require_permission("inventory:write"))):
    item = await _get_or_404(session, Environment, item_id)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    await session.flush()
    await WorkspaceBuilder(session).sync_all()
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/environments/{item_id}", status_code=204)
async def delete_environment(item_id: str, session: DbSession,
                             _: User = Depends(require_permission("inventory:write"))):
    await session.delete(await _get_or_404(session, Environment, item_id))
    await session.flush()
    await WorkspaceBuilder(session).sync_all()
    await session.commit()
    return Response(status_code=204)


async def _validate_server_refs(session: DbSession, payload: ServerCreate) -> None:
    await _get_or_404(session, System, payload.system_id)
    await _get_or_404(session, Environment, payload.environment_id)
    if payload.credential_id:
        credential = await _get_or_404(session, Credential, payload.credential_id)
        if not credential.is_active:
            raise HTTPException(status_code=422, detail="Credential is inactive")
        if credential.system_id not in {None, payload.system_id}:
            raise HTTPException(status_code=422, detail="Credential belongs to another System")


@router.get("/servers", response_model=list[ServerOut])
async def list_servers(session: DbSession, _: CurrentUser, response: Response,
                       pagination: PaginationDep,
                       q: str = "", status: str | None = None,
                       environment_id: str | None = None, system_id: str | None = None,
                       sort: str = Query("hostname"), direction: str = Query("asc")):
    statement = select(Server)
    if q:
        statement = statement.where(or_(Server.hostname.ilike(f"%{q}%"),
                                        Server.ip_address.ilike(f"%{q}%")))
    if status:
        statement = statement.where(Server.status == status)
    if environment_id:
        statement = statement.where(Server.environment_id == environment_id)
    if system_id:
        statement = statement.where(Server.system_id == system_id)
    total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    set_pagination_headers(response, total or 0, pagination)
    column = {"hostname": Server.hostname, "ip_address": Server.ip_address,
              "status": Server.status, "os": Server.os,
              "updated_at": Server.updated_at}.get(sort, Server.hostname)
    order = column.desc() if direction == "desc" else column.asc()
    return list((await session.scalars(
        statement.order_by(order).offset(pagination.offset).limit(pagination.page_size)
    )).unique().all())


@router.get("/servers/import-template")
async def server_import_template(
    _: User = Depends(require_permission("inventory:write")),
):
    return template_response("servers")


@router.post("/servers/import")
async def import_servers(
    session: DbSession,
    file: UploadFile = File(...),
    _: User = Depends(require_permission("inventory:write")),
) -> dict:
    rows = read_rows(await file.read(5 * 1024 * 1024 + 1), "servers")
    systems = {item.code.casefold(): item for item in (await session.scalars(select(System))).all()}
    environments = {item.name.casefold(): item for item in
                    (await session.scalars(select(Environment))).all()}
    credentials = list((await session.scalars(select(Credential))).all())
    created = updated = 0
    errors: list[dict] = []
    touched: set[str] = set()
    for row_number, row in rows:
        try:
            system = systems.get(str(row.get("system_code") or "").strip().casefold())
            environment = environments.get(str(row.get("environment") or "").strip().casefold())
            if system is None or environment is None:
                raise ValueError("System code or Environment name was not found")
            credential_name = str(row.get("credential_name") or "").strip()
            credential = next((item for item in credentials if item.name.casefold() ==
                               credential_name.casefold() and item.system_id in {None, system.id}), None)
            if credential_name and credential is None:
                raise ValueError("Shared SSH credential was not found in this System")
            payload = ServerCreate.model_validate({
                "system_id": system.id, "environment_id": environment.id,
                "credential_id": credential.id if credential else None,
                "hostname": str(row.get("hostname") or "").strip(),
                "ip_address": str(row.get("ip_address") or "").strip(),
                "os": str(row.get("os") or "").strip(),
                "server_type": str(row.get("server_type") or "linux").strip().lower(),
                "role": str(row.get("role") or "").strip(),
                "description": str(row.get("description") or "").strip(),
                "tags": [value.strip() for value in str(row.get("tags") or "").split(",")
                         if value.strip()],
                "ssh_config": {"port": int(row.get("ssh_port") or 22)},
            })
            item = await session.scalar(select(Server).where(
                Server.system_id == system.id, Server.hostname == payload.hostname
            ))
            values = payload.model_dump()
            if item is None:
                item = Server(**values)
                session.add(item)
                created += 1
            else:
                for key, value in values.items():
                    setattr(item, key, value)
                updated += 1
            await session.flush()
            touched.add(system.id)
        except Exception as exc:
            errors.append({"row": row_number, "error": _safe_import_error(exc)})
    workspace = WorkspaceBuilder(session)
    for system_id in touched:
        await workspace.sync_system(system_id)
    await session.commit()
    return {"created": created, "updated": updated, "failed": len(errors), "errors": errors}


@router.get("/servers/{item_id}", response_model=ServerOut)
async def get_server(item_id: str, session: DbSession,
                     _: User = Depends(require_permission("inventory:read"))):
    return await _get_or_404(session, Server, item_id)


@router.post("/servers", response_model=ServerOut, status_code=201)
async def create_server(payload: ServerCreate, session: DbSession,
                        _: User = Depends(require_permission("inventory:write"))):
    await _validate_server_refs(session, payload)
    item = Server(**payload.model_dump())
    session.add(item)
    await session.flush()
    await WorkspaceBuilder(session).sync_system(item.system_id)
    await session.commit()
    await session.refresh(item)
    await session.refresh(item, attribute_names=["credential"])
    return item


@router.put("/servers/{item_id}", response_model=ServerOut)
async def update_server(item_id: str, payload: ServerCreate, session: DbSession,
                        _: User = Depends(require_permission("inventory:write"))):
    await _validate_server_refs(session, payload)
    item = await _get_or_404(session, Server, item_id)
    old_system_id = item.system_id
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    await session.flush()
    workspace = WorkspaceBuilder(session)
    await workspace.sync_system(item.system_id)
    if old_system_id != item.system_id:
        await workspace.sync_system(old_system_id)
    await session.commit()
    await session.refresh(item)
    await session.refresh(item, attribute_names=["credential"])
    return item


@router.delete("/servers/{item_id}", status_code=204)
async def delete_server(item_id: str, session: DbSession,
                        _: User = Depends(require_permission("inventory:write"))):
    item = await _get_or_404(session, Server, item_id)
    system_id = item.system_id
    await session.delete(item)
    await session.flush()
    await WorkspaceBuilder(session).sync_system(system_id)
    await session.commit()
    return Response(status_code=204)


@router.post("/servers/{item_id}/test-connection")
async def test_server_connection(item_id: str, session: DbSession,
                                 _: User = Depends(require_permission("inventory:write")),
                                 gateway: SshGateway = Depends(get_ssh_gateway)):
    server = await _get_or_404(session, Server, item_id)
    command = "Write-Output AIOPS_CONNECTION_OK" if "win" in server.os.lower() else \
        "printf AIOPS_CONNECTION_OK"
    try:
        result = await gateway.execute(server, command)
    except AppError:
        server.status = "offline"
        await session.commit()
        raise
    server.status = "online" if result.exit_code == 0 else "degraded"
    await session.flush()
    await WorkspaceBuilder(session).sync_system(server.system_id)
    await session.commit()
    return {"status": server.status, "latency_ms": result.duration_ms,
            "connected": result.exit_code == 0}


@router.get("/credentials", response_model=list[CredentialOut])
async def list_credentials(session: DbSession,
                           response: Response, pagination: PaginationDep,
                           _: User = Depends(require_permission("secret:read_metadata")), q: str = "",
                           system_id: str | None = None):
    statement = select(Credential).order_by(Credential.name)
    if q:
        statement = statement.where(Credential.name.ilike(f"%{q}%"))
    if system_id:
        statement = statement.where(Credential.system_id == system_id)
    total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    set_pagination_headers(response, total or 0, pagination)
    return list((await session.scalars(statement.offset(pagination.offset).limit(
        pagination.page_size))).all())


@router.post("/credentials", response_model=CredentialOut, status_code=201)
async def create_credential(payload: CredentialCreate, session: DbSession,
                            _: User = Depends(require_permission("secret:write")),
                            secret_manager: SecretManager = Depends(get_secret_manager)):
    if payload.system_id is not None:
        await _get_or_404(session, System, payload.system_id)
    item = Credential(name=payload.name, system_id=payload.system_id,
                      username=payload.secret_payload["username"], provider="local_aes256_gcm",
                      encrypted_payload=secret_manager.encrypt(payload.secret_payload),
                      metadata_json={
                          **payload.metadata_json,
                          "scope": "shared" if payload.system_id else "global",
                      })
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.put("/credentials/{item_id}", response_model=CredentialOut)
async def update_credential(item_id: str, payload: CredentialUpdate, session: DbSession,
                            _: User = Depends(require_permission("secret:write")),
                            secret_manager: SecretManager = Depends(get_secret_manager)):
    item = await _get_or_404(session, Credential, item_id)
    if payload.system_id is not None:
        await _get_or_404(session, System, payload.system_id)
    item.name = payload.name
    item.system_id = payload.system_id
    item.metadata_json = {
        **payload.metadata_json,
        "scope": "shared" if payload.system_id else "global",
    }
    item.is_active = payload.is_active
    if payload.secret_payload is not None:
        item.encrypted_payload = secret_manager.encrypt(payload.secret_payload)
    elif item.username != payload.username:
        secret = secret_manager.decrypt(item.encrypted_payload)
        secret["username"] = payload.username
        item.encrypted_payload = secret_manager.encrypt(secret)
    item.username = payload.username
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/credentials/{item_id}", status_code=204)
async def delete_credential(item_id: str, session: DbSession,
                            _: User = Depends(require_permission("secret:write"))):
    in_use = await session.scalar(select(Server.id).where(Server.credential_id == item_id).limit(1))
    if in_use:
        raise HTTPException(status_code=409, detail="Credential is referenced by a server")
    default_in_use = await session.scalar(select(System.id).where(
        System.default_credential_id == item_id
    ).limit(1))
    if default_in_use:
        raise HTTPException(status_code=409, detail="Credential is a System default")
    await session.delete(await _get_or_404(session, Credential, item_id))
    await session.commit()
    return Response(status_code=204)
