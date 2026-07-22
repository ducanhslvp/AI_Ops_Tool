from typing import Annotated

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import DbSession, get_server_or_404, require_permission
from app.core.config import Settings, get_settings
from app.domain.models import User
from app.schemas.discovery import ProfileWrite, SimulationCommandWrite
from app.services.development_test_registry import DevelopmentTestRegistry
from app.services.tool_registry import ToolRegistry

router = APIRouter(prefix="/development", tags=["development"])


class TestProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: str = Field(pattern=r"^[a-z0-9_]+$", max_length=80)


def development_settings() -> Settings:
    settings = get_settings()
    if settings.app_env != "development" or settings.ssh_transport != "local_simulation":
        raise HTTPException(status_code=404, detail="Development test adapter is unavailable")
    return settings


DevSettings = Annotated[Settings, Depends(development_settings)]


def registry(settings: Settings) -> DevelopmentTestRegistry:
    root = Path(settings.local_test_snapshot_path)
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[4] / root
    return DevelopmentTestRegistry(root, ToolRegistry())


@router.get("/status")
async def development_status(
    settings: DevSettings,
    _: User = Depends(require_permission("inventory:read")),
) -> dict:
    return {
        "enabled": True,
        "transport": "local_simulation",
        "profiles": registry(settings).profiles(),
        "active_profile": registry(settings).read().get("active_profile", "healthy"),
    }


@router.get("/profiles")
async def list_profiles(settings: DevSettings,
                        _: User = Depends(require_permission("inventory:read"))) -> list[dict]:
    return registry(settings).profiles()


@router.put("/profiles/{profile_id}")
async def save_profile(profile_id: str, payload: ProfileWrite, settings: DevSettings,
                       _: User = Depends(require_permission("inventory:write"))) -> dict:
    if profile_id != payload.id:
        raise HTTPException(status_code=422, detail="Profile id does not match the route")
    return await registry(settings).upsert_profile(payload)


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(profile_id: str, settings: DevSettings,
                         _: User = Depends(require_permission("inventory:write"))) -> Response:
    await registry(settings).delete_profile(profile_id)
    return Response(status_code=204)


@router.put("/profiles/{profile_id}/active")
async def activate_profile(profile_id: str, settings: DevSettings,
                           _: User = Depends(require_permission("tool:execute"))) -> dict:
    await registry(settings).activate(profile_id)
    return {"active_profile": profile_id}


@router.get("/commands")
async def list_commands(settings: DevSettings, profile_id: str | None = None,
                        _: User = Depends(require_permission("inventory:read"))) -> list[dict]:
    return registry(settings).commands(profile_id)


@router.put("/commands/{command_id}")
async def save_command(command_id: str, payload: SimulationCommandWrite, settings: DevSettings,
                       _: User = Depends(require_permission("inventory:write"))) -> dict:
    if command_id != payload.id:
        raise HTTPException(status_code=422, detail="Command id does not match the route")
    return await registry(settings).upsert_command(payload)


@router.delete("/commands/{profile_id}/{command_id}", status_code=204)
async def delete_command(profile_id: str, command_id: str, settings: DevSettings,
                         _: User = Depends(require_permission("inventory:write"))) -> Response:
    await registry(settings).delete_command(profile_id, command_id)
    return Response(status_code=204)


@router.put("/servers/{server_id}/profile")
async def set_server_profile(
    server_id: str,
    payload: TestProfileUpdate,
    session: DbSession,
    settings: DevSettings,
    _: User = Depends(require_permission("tool:execute")),
) -> dict:
    profiles = {item["id"] for item in registry(settings).profiles()}
    if payload.profile not in profiles:
        raise HTTPException(status_code=422, detail="Unknown development test profile")
    server = await get_server_or_404(session, server_id)
    server.ssh_config = {**(server.ssh_config or {}), "test_profile": payload.profile}
    await session.commit()
    return {"server_id": server.id, "profile": payload.profile}
