import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from app.core.exceptions import AppError
from app.schemas.discovery import ProfileWrite, SimulationCommandWrite
from app.services.tool_registry import ToolRegistry


class DevelopmentTestRegistry:
    """Atomic development snapshot administration over registered Tool DSL actions."""

    def __init__(self, root: Path, tools: ToolRegistry) -> None:
        self.root = root.resolve()
        self.manifest_path = self.root / "profiles.json"
        self.tools = tools
        if not self.manifest_path.is_file():
            raise RuntimeError("Development profile manifest is unavailable")

    def read(self) -> dict[str, Any]:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    async def save(self, manifest: dict[str, Any]) -> None:
        data = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

        def atomic_write() -> None:
            temporary = self.manifest_path.with_suffix(".json.tmp")
            temporary.write_text(data, encoding="utf-8")
            temporary.replace(self.manifest_path)

        await asyncio.to_thread(atomic_write)

    def profiles(self) -> list[dict[str, Any]]:
        manifest = self.read()
        active = manifest.get("active_profile", "healthy")
        return [
            {"id": profile_id, "name": value["name"],
             "description": value.get("description", ""), "is_active": profile_id == active}
            for profile_id, value in manifest["profiles"].items()
        ]

    async def upsert_profile(self, payload: ProfileWrite) -> dict[str, Any]:
        manifest = self.read()
        current = manifest["profiles"].get(payload.id, {})
        manifest["profiles"][payload.id] = {
            "name": payload.name,
            "description": payload.description,
            "overrides": current.get("overrides", {}),
            "exit_codes": current.get("exit_codes", {}),
        }
        await self.save(manifest)
        (self.root / payload.id).mkdir(parents=True, exist_ok=True)
        return next(item for item in self.profiles() if item["id"] == payload.id)

    async def delete_profile(self, profile_id: str) -> None:
        if profile_id == "healthy":
            raise AppError("The healthy fallback profile cannot be deleted", 409)
        manifest = self.read()
        if profile_id not in manifest["profiles"]:
            raise AppError("Development profile not found", 404)
        del manifest["profiles"][profile_id]
        manifest["commands"] = [
            command for command in manifest.get("commands", [])
            if command.get("profile_id") != profile_id
        ]
        if manifest.get("active_profile") == profile_id:
            manifest["active_profile"] = "healthy"
        await self.save(manifest)
        directory = (self.root / profile_id).resolve()
        if self.root in directory.parents and directory.is_dir():
            await asyncio.to_thread(shutil.rmtree, directory)

    async def activate(self, profile_id: str) -> None:
        manifest = self.read()
        if profile_id not in manifest["profiles"]:
            raise AppError("Development profile not found", 404)
        manifest["active_profile"] = profile_id
        await self.save(manifest)

    def commands(self, profile_id: str | None = None) -> list[dict[str, Any]]:
        manifest = self.read()
        selected = profile_id or manifest.get("active_profile", "healthy")
        if selected not in manifest["profiles"]:
            raise AppError("Development profile not found", 404)
        records: list[dict[str, Any]] = []
        for command in manifest.get("commands", []):
            if command["profile_id"] != selected:
                continue
            rendered = self.tools.render_command(
                command["action"], command["os_name"], command.get("arguments", {})
            )
            path = self._snapshot_path(command["profile_id"], command["id"])
            records.append({**command, "command": rendered,
                            "output": path.read_text(encoding="utf-8") if path.is_file() else ""})
        return records

    async def upsert_command(self, payload: SimulationCommandWrite) -> dict[str, Any]:
        manifest = self.read()
        if payload.profile_id not in manifest["profiles"]:
            raise AppError("Development profile not found", 404)
        rendered = self.tools.render_command(payload.action, payload.os_name, payload.arguments)
        record = payload.model_dump(exclude={"output", "exit_code"})
        record["command"] = rendered
        commands = [item for item in manifest.get("commands", []) if not (
            item["id"] == payload.id and item["profile_id"] == payload.profile_id
        )]
        commands.append({key: value for key, value in record.items() if key != "command"})
        manifest["commands"] = commands
        profile = manifest["profiles"][payload.profile_id]
        profile.setdefault("exit_codes", {})[payload.id] = payload.exit_code
        await self.save(manifest)
        path = self._snapshot_path(payload.profile_id, payload.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_text, payload.output, encoding="utf-8")
        return {**record, "exit_code": payload.exit_code, "output": payload.output}

    async def delete_command(self, profile_id: str, command_id: str) -> None:
        manifest = self.read()
        before = len(manifest.get("commands", []))
        manifest["commands"] = [item for item in manifest.get("commands", []) if not (
            item["id"] == command_id and item["profile_id"] == profile_id
        )]
        if len(manifest["commands"]) == before:
            raise AppError("Simulation command not found", 404)
        manifest["profiles"].get(profile_id, {}).get("exit_codes", {}).pop(command_id, None)
        await self.save(manifest)
        path = self._snapshot_path(profile_id, command_id)
        if path.is_file():
            await asyncio.to_thread(path.unlink)

    def _snapshot_path(self, profile_id: str, command_id: str) -> Path:
        path = (self.root / profile_id / f"{command_id}.txt").resolve()
        if self.root not in path.parents:
            raise AppError("Snapshot path escaped the development root", 403)
        return path
