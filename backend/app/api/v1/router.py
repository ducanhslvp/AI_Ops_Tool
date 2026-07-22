from fastapi import APIRouter

from app.api.v1.routes import (
    admin, ai, audit, auth, dashboard, development, discovery, health, inventory, knowledge, memory, policy, reports, search,
    tools,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(inventory.router)
api_router.include_router(tools.router)
api_router.include_router(ai.router)
api_router.include_router(memory.router)
api_router.include_router(policy.router)
api_router.include_router(audit.router)
api_router.include_router(reports.router)
api_router.include_router(admin.router)
api_router.include_router(dashboard.router)
api_router.include_router(knowledge.router)
api_router.include_router(search.router)
api_router.include_router(development.router)
api_router.include_router(discovery.router)
