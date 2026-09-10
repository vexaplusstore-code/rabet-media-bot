from __future__ import annotations

import asyncio
import logging

from .bot import DownloaderBot
from .config import Settings


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(DownloaderBot(settings).run())


if __name__ == "__main__":
    main()

