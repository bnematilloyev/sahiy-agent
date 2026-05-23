"""Typing chat action loop with automatic cancel."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from telegram.error import Forbidden, NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def typing_indicator(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    interval_seconds: float,
) -> AsyncIterator[None]:
    task = asyncio.create_task(_typing_loop(context, chat_id, interval_seconds))
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _typing_loop(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    interval_seconds: float,
) -> None:
    try:
        while True:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except Forbidden:
                pass
            except (TimedOut, NetworkError) as exc:
                logger.warning("send_chat_action skipped (network): %s", exc)
            except TelegramError as exc:
                logger.warning("send_chat_action skipped: %s", exc)
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        raise
