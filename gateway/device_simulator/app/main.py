from __future__ import annotations

import asyncio
import logging

from app.runner import DeviceSimulatorRunner
from app.settings import load_runtime_settings


def configure_logging() -> None:
    """Configure process-wide console logging for the simulator.

    :return: None.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def _async_main() -> None:
    """Load settings and run the simulator until cancelled.

    :return: This coroutine normally runs forever.
    """
    settings = load_runtime_settings()
    runner = DeviceSimulatorRunner(settings)
    await runner.run_forever()


def main() -> None:
    """Start the simulator command-line entrypoint.

    :return: None.
    """
    configure_logging()
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
