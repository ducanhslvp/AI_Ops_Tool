import asyncio
import os
import tempfile
from pathlib import Path
from typing import Protocol


class WorkspaceStorage(Protocol):
    root: Path

    async def write_text(self, relative_path: str, content: str) -> Path: ...
    async def write_bytes(self, relative_path: str, content: bytes) -> Path: ...
    async def read_text(self, relative_path: str) -> str: ...
    async def exists(self, relative_path: str) -> bool: ...
    async def remove(self, relative_path: str, *, recursive: bool = False) -> None: ...
    def resolve(self, relative_path: str) -> Path: ...


class LocalWorkspaceStorage:
    """Local workspace storage with containment checks and atomic file replacement."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Workspace path escapes the configured root")
        return candidate

    async def write_text(self, relative_path: str, content: str) -> Path:
        return await self._write(relative_path, content.encode("utf-8"))

    async def write_bytes(self, relative_path: str, content: bytes) -> Path:
        return await self._write(relative_path, content)

    async def _write(self, relative_path: str, content: bytes) -> Path:
        target = self.resolve(relative_path)

        def write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.parent.is_symlink():
                raise ValueError("Workspace parent cannot be a symlink")
            fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

        await asyncio.to_thread(write)
        return target

    async def read_text(self, relative_path: str) -> str:
        path = self.resolve(relative_path)
        return await asyncio.to_thread(path.read_text, encoding="utf-8")

    async def exists(self, relative_path: str) -> bool:
        return await asyncio.to_thread(self.resolve(relative_path).exists)

    async def remove(self, relative_path: str, *, recursive: bool = False) -> None:
        path = self.resolve(relative_path)
        if not path.exists():
            return
        if path.is_symlink():
            raise ValueError("Refusing to remove a workspace symlink")

        def remove_path() -> None:
            if path.is_dir():
                if not recursive:
                    path.rmdir()
                    return
                for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
                    if child.is_symlink():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                    else:
                        child.unlink()
                path.rmdir()
            else:
                path.unlink()

        await asyncio.to_thread(remove_path)
