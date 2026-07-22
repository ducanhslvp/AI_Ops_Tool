from fastapi import APIRouter
from sqlalchemy import text

from app.api.dependencies import DbSession

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health(session: DbSession) -> dict:
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
