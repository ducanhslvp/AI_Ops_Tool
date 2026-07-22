from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Credential, Environment, Server, System
from app.repositories.base import Repository


class SystemRepository(Repository[System]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, System)


class ServerRepository(Repository[Server]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Server)

    async def list_by_system(self, system_id: str) -> list[Server]:
        return await self.list(select(Server).where(Server.system_id == system_id))


class EnvironmentRepository(Repository[Environment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Environment)


class CredentialRepository(Repository[Credential]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Credential)
