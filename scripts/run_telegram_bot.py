#!/usr/bin/env python3
"""Run the Telegram bot (test interface for the AI service layer)."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.channels.telegram.bot import TelegramBot
from app.core.config import get_settings
from app.core.database import dispose_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    bot = TelegramBot(settings)

    stop_event = asyncio.Event()

    def _shutdown(*_args):
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _shutdown)
    except NotImplementedError:
        pass

    await bot.start()
    try:
        await stop_event.wait()
    finally:
        await bot.stop()
        await dispose_engine()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
