"""Adaptive streaming display for Telegram edit_message_text."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from telegram import Message
from telegram.error import Forbidden, NetworkError, RetryAfter, TelegramError, TimedOut

from app.channels.telegram.messenger import TELEGRAM_MAX_MESSAGE_LEN, TelegramMessenger

logger = logging.getLogger(__name__)

STREAM_TRAIL_FRAMES = (" ·", " ··", " ···", " ··")
STREAM_TRAIL_INTERVAL = 0.4


@dataclass(frozen=True)
class StreamConfig:
    chars_per_tick: int
    tick_delay: float
    min_edit_gap: float
    show_cursor: bool


class SmoothStreamSession:
    """Adaptive pacing for LLM token streaming over Telegram message edits."""

    def __init__(
        self,
        message: Message,
        messenger: TelegramMessenger,
        config: StreamConfig,
    ) -> None:
        self._message = message
        self._messenger = messenger
        self._config = config
        self._full_response = ""
        self._displayed_response = ""
        self._stream_done = False
        self._last_pushed_len = 0
        self._last_frame = ""
        self._last_edit_at = 0.0
        self._trail_idx = 0
        self._task = asyncio.create_task(self._smooth_display())

    async def enqueue(self, accumulated: str) -> None:
        display = self._messenger.clip_text(accumulated)
        if len(display) > self._last_pushed_len:
            self._full_response = display
            self._last_pushed_len = len(display)

    async def finish(self, final_text: str) -> None:
        await self.enqueue(final_text)
        self._stream_done = True
        try:
            await asyncio.wait_for(self._task, timeout=120.0)
        except asyncio.TimeoutError:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    @staticmethod
    def _take_chunk(remaining: str, target_chars: int) -> str:
        if not remaining:
            return ""
        if len(remaining) <= target_chars:
            return remaining
        window_start = max(1, int(target_chars * 0.75))
        window_end = min(len(remaining), int(target_chars * 1.25) + 1)
        slice_ = remaining[window_start:window_end]
        space_pos = slice_.rfind(" ")
        if space_pos != -1:
            return remaining[: window_start + space_pos + 1]
        space_pos = remaining.find(" ", target_chars)
        if space_pos != -1 and space_pos < target_chars * 2:
            return remaining[: space_pos + 1]
        return remaining[:target_chars]

    def _adaptive_chunk_size(self, lag: int) -> int:
        base = max(1, self._config.chars_per_tick)
        if self._stream_done:
            if lag > 200:
                return max(base * 8, lag // 4)
            if lag > 80:
                return base * 4
            if lag > 30:
                return base * 2
            return base
        if lag > 120:
            return base * 3
        if lag > 50:
            return base * 2
        return base

    def _trail(self, *, show: bool) -> str:
        if not show or not self._config.show_cursor:
            return ""
        return STREAM_TRAIL_FRAMES[self._trail_idx % len(STREAM_TRAIL_FRAMES)]

    def _build_frame(self, *, show_trail: bool) -> str:
        body = self._displayed_response
        trail = self._trail(show=show_trail)
        if not body:
            return trail or "…"
        body = self._messenger.clip_text(body)
        if trail and len(body) + len(trail) <= TELEGRAM_MAX_MESSAGE_LEN:
            return body + trail
        return body

    async def _try_edit(self, *, show_cursor: bool) -> bool:
        frame = self._build_frame(show_trail=show_cursor)
        if frame == self._last_frame:
            return True
        try:
            await self._message.edit_text(frame)
            self._last_frame = frame
            self._last_edit_at = time.monotonic()
            return True
        except RetryAfter as exc:
            backoff = float(getattr(exc, "retry_after", 1.0)) + 0.05
            self._last_edit_at = time.monotonic() + backoff
            await asyncio.sleep(min(backoff, 2.0))
            return False
        except Forbidden:
            return False
        except (TimedOut, NetworkError):
            self._last_edit_at = time.monotonic()
            return False
        except TelegramError as exc:
            msg = str(exc).lower()
            if "not modified" in msg:
                self._last_frame = frame
                return True
            logger.warning("stream edit_text failed: %s", exc)
            return False

    async def _smooth_display(self) -> None:
        tick_delay = self._config.tick_delay
        min_edit_gap = self._config.min_edit_gap

        while True:
            now = time.monotonic()
            remaining = self._full_response[len(self._displayed_response) :]

            if not self._full_response and not self._stream_done:
                await asyncio.sleep(tick_delay)
                continue

            gap_ready = (now - self._last_edit_at) >= min_edit_gap
            edited = False
            if remaining and gap_ready:
                chunk_size = self._adaptive_chunk_size(len(remaining))
                chunk = self._take_chunk(remaining, chunk_size)
                self._displayed_response += chunk
                self._trail_idx += 1
                at_end = (
                    self._stream_done
                    and self._displayed_response == self._full_response
                )
                await self._try_edit(show_cursor=not at_end)
                edited = True

            if (
                not edited
                and not self._stream_done
                and self._displayed_response
                and (now - self._last_edit_at) >= STREAM_TRAIL_INTERVAL
            ):
                self._trail_idx += 1
                await self._try_edit(show_cursor=True)

            if self._stream_done and self._displayed_response == self._full_response:
                await self._try_edit(show_cursor=False)
                break

            await asyncio.sleep(tick_delay)
