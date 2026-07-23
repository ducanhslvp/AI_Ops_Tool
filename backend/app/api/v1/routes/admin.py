from hashlib import sha256
from typing import Annotated, Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import AIGateway
from app.ai.models import ProviderHealth, ProviderStatus
from app.api.dependencies import DbSession, get_gateway, require_permission
from app.core.security import hash_password
from app.domain.models import (
    AiCommandApproval, AiProviderConfiguration, NotificationChannel, Permission,
    PlatformSetting, Plugin, ReportTemplate, Role, Server, SshGatewayProfile, System, User,
)
from app.schemas.admin import (
    AiProviderConfigOut, AiProviderWrite, NotificationOut, NotificationWrite,
    PermissionAdminOut, PermissionWrite, PluginOut, PluginWrite, ReportTemplateOut,
    ReportTemplateWrite, RoleAdminOut, RoleWrite, SettingOut, SettingWrite, SshGatewayOut,
    SshCommandOut, SshCommandWrite, SshGatewayWrite, UserAdminOut, UserCreate, UserUpdate,
)
from app.schemas.common import PaginationDep, set_pagination_headers
from app.services.ai_provider_runtime import apply_health, provider_config_from_record
from app.services.command_guard import SshCommandGuard

router = APIRouter(prefix="/admin", tags=["administration"])
AdminUser = Annotated[User, Depends(require_permission("*"))]
ModelT = TypeVar("ModelT")


async def _get(session: AsyncSession, model: type[ModelT], item_id: str) -> ModelT:
    item = await session.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return item


def _apply(item: Any, payload: BaseModel, *, exclude: set[str] | None = None) -> None:
    for key, value in payload.model_dump(exclude=exclude or set()).items():
        setattr(item, key, value)


@router.get("/permissions", response_model=list[PermissionAdminOut])
async def list_permissions(session: DbSession, _: AdminUser, response: Response,
                           pagination: PaginationDep, q: str = ""):
    statement = select(Permission).order_by(Permission.code)
    if q:
        statement = statement.where(Permission.code.ilike(f"%{q}%"))
    total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    set_pagination_headers(response, total or 0, pagination)
    return list((await session.scalars(statement.offset(pagination.offset).limit(
        pagination.page_size))).all())


@router.post("/permissions", response_model=PermissionAdminOut, status_code=201)
async def create_permission(payload: PermissionWrite, session: DbSession, _: AdminUser):
    item = Permission(**payload.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.put("/permissions/{item_id}", response_model=PermissionAdminOut)
async def update_permission(item_id: str, payload: PermissionWrite, session: DbSession, _: AdminUser):
    item = await _get(session, Permission, item_id)
    _apply(item, payload)
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/permissions/{item_id}", status_code=204)
async def delete_permission(item_id: str, session: DbSession, _: AdminUser):
    await session.delete(await _get(session, Permission, item_id))
    await session.commit()
    return Response(status_code=204)


def _role_out(role: Role) -> RoleAdminOut:
    return RoleAdminOut.model_validate({
        **role.__dict__, "permission_ids": [permission.id for permission in role.permissions]
    })


@router.get("/roles", response_model=list[RoleAdminOut])
async def list_roles(session: DbSession, _: AdminUser, response: Response,
                     pagination: PaginationDep, q: str = ""):
    statement = select(Role).order_by(Role.name)
    if q:
        statement = statement.where(Role.name.ilike(f"%{q}%"))
    total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    set_pagination_headers(response, total or 0, pagination)
    return [_role_out(item) for item in (await session.scalars(statement.offset(
        pagination.offset).limit(pagination.page_size))).unique().all()]


async def _permissions(session: AsyncSession, ids: list[str]) -> list[Permission]:
    values = list((await session.scalars(select(Permission).where(Permission.id.in_(ids)))).all())
    if len(values) != len(set(ids)):
        raise HTTPException(status_code=422, detail="One or more permissions do not exist")
    return values


@router.post("/roles", response_model=RoleAdminOut, status_code=201)
async def create_role(payload: RoleWrite, session: DbSession, _: AdminUser):
    role = Role(name=payload.name, description=payload.description,
                permissions=await _permissions(session, payload.permission_ids))
    session.add(role)
    await session.commit()
    await session.refresh(role)
    return _role_out(role)


@router.put("/roles/{item_id}", response_model=RoleAdminOut)
async def update_role(item_id: str, payload: RoleWrite, session: DbSession, _: AdminUser):
    role = await _get(session, Role, item_id)
    role.name = payload.name
    role.description = payload.description
    role.permissions = await _permissions(session, payload.permission_ids)
    await session.commit()
    await session.refresh(role)
    return _role_out(role)


@router.delete("/roles/{item_id}", status_code=204)
async def delete_role(item_id: str, session: DbSession, _: AdminUser):
    await session.delete(await _get(session, Role, item_id))
    await session.commit()
    return Response(status_code=204)


def _user_out(user: User) -> UserAdminOut:
    return UserAdminOut.model_validate({**user.__dict__, "role_name": user.role.name})


@router.get("/users", response_model=list[UserAdminOut])
async def list_users(session: DbSession, _: AdminUser, response: Response,
                     pagination: PaginationDep, q: str = ""):
    statement = select(User).order_by(User.email)
    if q:
        statement = statement.where(or_(User.email.ilike(f"%{q}%"),
                                        User.full_name.ilike(f"%{q}%")))
    total = await session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    set_pagination_headers(response, total or 0, pagination)
    return [_user_out(item) for item in (await session.scalars(statement.offset(
        pagination.offset).limit(pagination.page_size))).unique().all()]


@router.post("/users", response_model=UserAdminOut, status_code=201)
async def create_user(payload: UserCreate, session: DbSession, _: AdminUser):
    await _get(session, Role, payload.role_id)
    user = User(email=str(payload.email).lower(), full_name=payload.full_name,
                password_hash=hash_password(payload.password), role_id=payload.role_id,
                is_active=payload.is_active)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _user_out(user)


@router.put("/users/{item_id}", response_model=UserAdminOut)
async def update_user(item_id: str, payload: UserUpdate, session: DbSession, actor: AdminUser):
    user = await _get(session, User, item_id)
    values = payload.model_dump(exclude_unset=True, exclude={"password"})
    if values.get("role_id"):
        await _get(session, Role, values["role_id"])
    if "email" in values:
        values["email"] = str(values["email"]).lower()
    for key, value in values.items():
        setattr(user, key, value)
    if payload.password:
        user.password_hash = hash_password(payload.password)
    if user.id == actor.id and user.is_active is False:
        raise HTTPException(status_code=409, detail="You cannot disable your own account")
    await session.commit()
    await session.refresh(user)
    return _user_out(user)


@router.delete("/users/{item_id}", status_code=204)
async def delete_user(item_id: str, session: DbSession, actor: AdminUser):
    if item_id == actor.id:
        raise HTTPException(status_code=409, detail="You cannot delete your own account")
    await session.delete(await _get(session, User, item_id))
    await session.commit()
    return Response(status_code=204)


def _ssh_command_out(row) -> SshCommandOut:
    item, email, system_code, hostname = row
    return SshCommandOut.model_validate({
        **item.__dict__, "user_email": email, "system_code": system_code,
        "server_hostname": hostname,
    })


async def _validated_ssh_command_values(
    session: AsyncSession, payload: SshCommandWrite, actor: User,
) -> dict:
    user = await _get(session, User, payload.user_id or actor.id)
    if (payload.system_id is None) != (payload.server_id is None):
        raise HTTPException(
            status_code=422,
            detail="Select both System and Server for a scoped rule, or neither for a Global rule",
        )
    system = await _get(session, System, payload.system_id) if payload.system_id else None
    server = await _get(session, Server, payload.server_id) if payload.server_id else None
    if server is not None and system is not None and server.system_id != system.id:
        raise HTTPException(status_code=422, detail="Server does not belong to the selected System")
    # Global rules are validated against the Linux command contract. Windows rules remain
    # server-scoped because the two command languages intentionally have different allowlists.
    command = SshCommandGuard().validate(payload.command, server.os if server else "linux").command
    return {
        "user_id": user.id,
        "system_id": system.id if system else None,
        "server_id": server.id if server else None,
        "command": command, "command_hash": sha256(command.encode("utf-8")).hexdigest(),
        "effect": payload.effect, "description": payload.description,
        "is_active": payload.is_active,
    }


@router.get("/ssh-commands", response_model=list[SshCommandOut])
async def list_ssh_commands(
    session: DbSession, _: AdminUser, response: Response, pagination: PaginationDep,
    q: str = "", effect: str | None = None,
) -> list[SshCommandOut]:
    statement = select(AiCommandApproval, User.email, System.code, Server.hostname).join(
        User, User.id == AiCommandApproval.user_id
    ).outerjoin(System, System.id == AiCommandApproval.system_id).outerjoin(
        Server, Server.id == AiCommandApproval.server_id
    )
    if q:
        statement = statement.where(or_(
            AiCommandApproval.command.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"),
            System.code.ilike(f"%{q}%"), Server.hostname.ilike(f"%{q}%"),
        ))
    if effect:
        statement = statement.where(AiCommandApproval.effect == effect)
    total = await session.scalar(select(func.count()).select_from(
        statement.order_by(None).subquery()
    )) or 0
    set_pagination_headers(response, total, pagination)
    rows = (await session.execute(statement.order_by(
        AiCommandApproval.last_used_at.desc(), AiCommandApproval.updated_at.desc()
    ).offset(pagination.offset).limit(pagination.page_size))).all()
    return [_ssh_command_out(row) for row in rows]


@router.post("/ssh-commands", response_model=SshCommandOut, status_code=201)
async def create_ssh_command(
    payload: SshCommandWrite, session: DbSession, actor: AdminUser,
) -> SshCommandOut:
    values = await _validated_ssh_command_values(session, payload, actor)
    conflict = await session.scalar(select(AiCommandApproval.id).where(
        AiCommandApproval.user_id == values["user_id"],
        AiCommandApproval.system_id.is_(None) if values["system_id"] is None
        else AiCommandApproval.system_id == values["system_id"],
        AiCommandApproval.server_id.is_(None) if values["server_id"] is None
        else AiCommandApproval.server_id == values["server_id"],
        AiCommandApproval.command_hash == values["command_hash"],
    ))
    if conflict:
        raise HTTPException(status_code=409, detail="This scoped SSH command already exists")
    item = AiCommandApproval(**values)
    session.add(item)
    await session.commit()
    row = (await session.execute(select(
        AiCommandApproval, User.email, System.code, Server.hostname
    ).join(User, User.id == AiCommandApproval.user_id).outerjoin(
        System, System.id == AiCommandApproval.system_id
    ).outerjoin(Server, Server.id == AiCommandApproval.server_id).where(
        AiCommandApproval.id == item.id
    ))).one()
    return _ssh_command_out(row)


@router.put("/ssh-commands/{item_id}", response_model=SshCommandOut)
async def update_ssh_command(
    item_id: str, payload: SshCommandWrite, session: DbSession, actor: AdminUser,
) -> SshCommandOut:
    item = await _get(session, AiCommandApproval, item_id)
    values = await _validated_ssh_command_values(session, payload, actor)
    conflict = await session.scalar(select(AiCommandApproval.id).where(
        AiCommandApproval.id != item.id,
        AiCommandApproval.user_id == values["user_id"],
        AiCommandApproval.system_id.is_(None) if values["system_id"] is None
        else AiCommandApproval.system_id == values["system_id"],
        AiCommandApproval.server_id.is_(None) if values["server_id"] is None
        else AiCommandApproval.server_id == values["server_id"],
        AiCommandApproval.command_hash == values["command_hash"],
    ))
    if conflict:
        raise HTTPException(status_code=409, detail="This scoped SSH command already exists")
    for key, value in values.items():
        setattr(item, key, value)
    await session.commit()
    row = (await session.execute(select(
        AiCommandApproval, User.email, System.code, Server.hostname
    ).join(User, User.id == AiCommandApproval.user_id).outerjoin(
        System, System.id == AiCommandApproval.system_id
    ).outerjoin(Server, Server.id == AiCommandApproval.server_id).where(
        AiCommandApproval.id == item.id
    ))).one()
    return _ssh_command_out(row)


@router.delete("/ssh-commands/{item_id}", status_code=204)
async def delete_ssh_command(item_id: str, session: DbSession, _: AdminUser) -> Response:
    await session.delete(await _get(session, AiCommandApproval, item_id))
    await session.commit()
    return Response(status_code=204)


RESOURCE_MAP = {
    "plugins": (Plugin, PluginWrite, PluginOut),
    "settings": (PlatformSetting, SettingWrite, SettingOut),
    "notifications": (NotificationChannel, NotificationWrite, NotificationOut),
    "ssh-gateways": (SshGatewayProfile, SshGatewayWrite, SshGatewayOut),
    "report-templates": (ReportTemplate, ReportTemplateWrite, ReportTemplateOut),
}


def _register_resource_routes(path: str, model: type, schema: type[BaseModel], output: type[BaseModel]):
    async def list_items(session: DbSession, _: AdminUser, response: Response,
                         pagination: PaginationDep, q: str = ""):
        order_column = model.name if hasattr(model, "name") else model.key
        statement = select(model)
        if q:
            statement = statement.where(order_column.ilike(f"%{q}%"))
        total = await session.scalar(select(func.count()).select_from(
            statement.order_by(None).subquery()))
        set_pagination_headers(response, total or 0, pagination)
        return list((await session.scalars(statement.order_by(order_column).offset(
            pagination.offset).limit(pagination.page_size))).all())

    async def create_item(payload: schema, session: DbSession, _: AdminUser):
        if model is SshGatewayProfile and payload.is_active:
            await session.execute(update(SshGatewayProfile).values(is_active=False))
        item = model(**payload.model_dump())
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item

    async def update_item(item_id: str, payload: schema, session: DbSession, _: AdminUser):
        item = await _get(session, model, item_id)
        if model is SshGatewayProfile and payload.is_active:
            await session.execute(update(SshGatewayProfile).where(
                SshGatewayProfile.id != item_id
            ).values(is_active=False))
        _apply(item, payload)
        await session.commit()
        await session.refresh(item)
        return item

    async def delete_item(item_id: str, session: DbSession, _: AdminUser):
        await session.delete(await _get(session, model, item_id))
        await session.commit()
        return Response(status_code=204)

    router.add_api_route(f"/{path}", list_items, methods=["GET"], response_model=list[output])
    router.add_api_route(f"/{path}", create_item, methods=["POST"], response_model=output,
                         status_code=201)
    router.add_api_route(f"/{path}/{{item_id}}", update_item, methods=["PUT"],
                         response_model=output)
    router.add_api_route(f"/{path}/{{item_id}}", delete_item, methods=["DELETE"], status_code=204)


for resource_path, (resource_model, write_schema, output_schema) in RESOURCE_MAP.items():
    _register_resource_routes(resource_path, resource_model, write_schema, output_schema)


@router.get("/ai-providers", response_model=list[AiProviderConfigOut])
async def list_ai_providers(session: DbSession, _: AdminUser, response: Response,
                            pagination: PaginationDep):
    total = await session.scalar(select(func.count(AiProviderConfiguration.id))) or 0
    set_pagination_headers(response, total, pagination)
    return list((await session.scalars(select(AiProviderConfiguration).order_by(
        AiProviderConfiguration.name).offset(pagination.offset).limit(
            pagination.page_size))).all())


@router.post("/ai-providers", response_model=AiProviderConfigOut, status_code=201)
async def create_ai_provider(payload: AiProviderWrite, session: DbSession, _: AdminUser):
    item = AiProviderConfiguration(**payload.model_dump())
    if item.is_active:
        await session.execute(update(AiProviderConfiguration).values(is_active=False))
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.put("/ai-providers/{item_id}", response_model=AiProviderConfigOut)
async def update_ai_provider(item_id: str, payload: AiProviderWrite,
                             session: DbSession, _: AdminUser):
    item = await _get(session, AiProviderConfiguration, item_id)
    if payload.is_active:
        await session.execute(update(AiProviderConfiguration).values(is_active=False))
    _apply(item, payload)
    await session.commit()
    await session.refresh(item)
    return item


@router.post("/ai-providers/{item_id}/activate", response_model=AiProviderConfigOut)
async def activate_ai_provider(item_id: str, session: DbSession, _: AdminUser,
                               gateway: AIGateway = Depends(get_gateway)):
    item = await _get(session, AiProviderConfiguration, item_id)
    if not item.enabled:
        raise HTTPException(status_code=409, detail="Disabled provider cannot be activated")
    config = provider_config_from_record(item)
    health = await gateway.manager.test_connection(config)
    apply_health(item, health)
    if health.status != ProviderStatus.ready:
        await session.commit()
        raise HTTPException(status_code=409, detail=health.detail or "Provider is not ready")
    await gateway.manager.load(item.name, config)
    await gateway.manager.switch(item.name, exclusive=item.exclusive_mode)
    await session.execute(update(AiProviderConfiguration).values(is_active=False))
    item.is_active = True
    await session.commit()
    await session.refresh(item)
    return item


@router.post("/ai-providers/{item_id}/test-connection", response_model=ProviderHealth)
async def test_ai_provider_connection(item_id: str, session: DbSession, _: AdminUser,
                                      gateway: AIGateway = Depends(get_gateway)):
    item = await _get(session, AiProviderConfiguration, item_id)
    if not item.enabled:
        raise HTTPException(status_code=409, detail="Disabled provider cannot be tested")
    config = provider_config_from_record(item)
    health = await gateway.manager.test_connection(config)
    apply_health(item, health)
    await session.commit()
    return health


@router.delete("/ai-providers/{item_id}", status_code=204)
async def delete_ai_provider(item_id: str, session: DbSession, _: AdminUser,
                             gateway: AIGateway = Depends(get_gateway)):
    item = await _get(session, AiProviderConfiguration, item_id)
    if item.is_active or item.name == gateway.manager.active_name:
        raise HTTPException(status_code=409, detail="Active provider cannot be deleted")
    if item.name in {info["name"] for info in gateway.providers()}:
        await gateway.manager.unload(item.name)
    await session.delete(item)
    await session.commit()
    return Response(status_code=204)
