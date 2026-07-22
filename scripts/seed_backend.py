import asyncio
import logging

from development_seed import seed_development_data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    asyncio.run(seed_development_data())
