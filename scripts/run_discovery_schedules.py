import asyncio
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.api.dependencies import get_secret_manager  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionFactory  # noqa: E402
from app.services.local_simulation_adapter import LocalSimulationAdapter  # noqa: E402
from app.services.ssh_gateway import SshGateway  # noqa: E402
from app.services.tool_registry import ToolRegistry  # noqa: E402
from app.workers.discovery_scheduler import run_due_discovery_schedules  # noqa: E402


async def main() -> None:
    settings = get_settings()
    adapter = (LocalSimulationAdapter(settings) if settings.test_features_enabled and
               settings.ssh_transport == "local_simulation" else None)
    async with AsyncSessionFactory() as session:
        completed = await run_due_discovery_schedules(
            session, ToolRegistry(), SshGateway(get_secret_manager(), adapter)
        )
    print(f"Completed {completed} due discovery schedule(s)")


if __name__ == "__main__":
    asyncio.run(main())
