"""Telegram transport helpers — retries, clipping, safe send/edit."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from telegram import InputMediaPhoto, Message, Update
from telegram.error import Forbidden, NetworkError, RetryAfter, TelegramError, TimedOut

from app.channels.telegram.keyboards import main_menu_keyboard

logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE_LEN = 4096
STREAM_CURSOR = "▌"


class TelegramMessenger:
    def __init__(self, *, send_retries: int) -> None:
        self._send_retries = send_retries

    @staticmethod
    def clip_text(text: str) -> str:
        if len(text) <= TELEGRAM_MAX_MESSAGE_LEN:
            return text
        return text[: TELEGRAM_MAX_MESSAGE_LEN - 1] + "…"

    def stream_frame_text(self, body: str, *, show_cursor: bool) -> str:
        if not body:
            body = "…"
        body = self.clip_text(body)
        if not show_cursor:
            return body
        suffix = STREAM_CURSOR
        if len(body) + len(suffix) <= TELEGRAM_MAX_MESSAGE_LEN:
            return body + suffix
        return self.clip_text(body[: TELEGRAM_MAX_MESSAGE_LEN - len(suffix)]) + suffix

    async def reply_text(
        self,
        update: Update,
        text: str,
        *,
        reply_markup: Any = None,
        lang: Optional[str] = None,
        attach_main_menu: bool = True,
    ) -> Optional[Message]:
        if not update.message:
            return None
        message = update.message
        user_id = update.effective_user.id if update.effective_user else "unknown"
        markup = reply_markup
        if markup is None and attach_main_menu:
            markup = main_menu_keyboard(lang or "uz_lat")
        display = text
        for attempt in range(1, self._send_retries + 1):
            try:
                return await message.reply_text(display, reply_markup=markup)
            except Forbidden:
                logger.info("User blocked bot, skipping reply user_id=%s", user_id)
                return None
            except (TimedOut, NetworkError) as exc:
                logger.warning(
                    "reply_text attempt %s/%s failed: %s",
                    attempt,
                    self._send_retries,
                    exc,
                )
                if attempt < self._send_retries:
                    await asyncio.sleep(1.5 * attempt)
            except TelegramError as exc:
                logger.warning("reply_text failed user_id=%s: %s", user_id, exc)
                return None
        return None

    async def reply_to_message(
        self,
        message: Message,
        text: str,
        *,
        reply_markup: Any = None,
    ) -> bool:
        display = self.clip_text(text.strip() or "…")
        for attempt in range(1, self._send_retries + 1):
            try:
                await message.reply_text(display, reply_markup=reply_markup)
                return True
            except Forbidden:
                return False
            except (TimedOut, NetworkError) as exc:
                logger.warning(
                    "reply_to_message attempt %s/%s failed: %s",
                    attempt,
                    self._send_retries,
                    exc,
                )
                if attempt < self._send_retries:
                    await asyncio.sleep(1.5 * attempt)
            except TelegramError as exc:
                logger.warning("reply_to_message failed: %s", exc)
                return False
        return False

    async def edit_message_text(
        self,
        message: Optional[Message],
        text: str,
        *,
        reply_markup: Any = None,
        allow_empty_strip: bool = True,
    ) -> bool:
        if message is None:
            return False
        if allow_empty_strip:
            display = self.clip_text(text.strip() or "…")
        else:
            display = self.clip_text(text)
        for attempt in range(1, self._send_retries + 1):
            try:
                await message.edit_text(display, reply_markup=reply_markup)
                return True
            except Forbidden:
                return False
            except (TimedOut, NetworkError) as exc:
                logger.warning(
                    "edit_text attempt %s/%s failed: %s",
                    attempt,
                    self._send_retries,
                    exc,
                )
                if attempt < self._send_retries:
                    await asyncio.sleep(1.5 * attempt)
            except TelegramError as exc:
                if "not modified" in str(exc).lower():
                    return True
                logger.warning("edit_text failed: %s", exc)
                return False
        return False

    async def send_product_photo(
        self,
        update: Update,
        photo_url: str,
        caption: str,
        *,
        reply_markup: Any = None,
        lang: str = "uz_lat",
    ) -> None:
        if not update.message or not photo_url:
            return
        display_caption = self.clip_text(caption[:1024])
        markup = reply_markup or main_menu_keyboard(lang)
        user_id = update.effective_user.id if update.effective_user else "unknown"
        for attempt in range(1, self._send_retries + 1):
            try:
                await update.message.reply_photo(
                    photo=photo_url,
                    caption=display_caption,
                    reply_markup=markup,
                )
                return
            except Forbidden:
                return
            except (TimedOut, NetworkError) as exc:
                logger.warning(
                    "reply_photo attempt %s/%s failed: %s",
                    attempt,
                    self._send_retries,
                    exc,
                )
                if attempt < self._send_retries:
                    await asyncio.sleep(1.5 * attempt)
            except TelegramError as exc:
                logger.warning("reply_photo failed user_id=%s: %s", user_id, exc)
                return

    async def send_media_group(self, update: Update, photo_urls: list) -> None:
        if not update.message or not photo_urls:
            return
        urls = [u for u in photo_urls if u and str(u).strip()][:10]
        if not urls:
            return
        try:
            media = [InputMediaPhoto(media=url) for url in urls]
            await update.message.reply_media_group(media=media)
        except TelegramError as exc:
            logger.warning("media_group send failed: %s", exc)
            try:
                await update.message.reply_photo(photo=urls[0])
            except TelegramError as exc2:
                logger.warning("single photo fallback failed: %s", exc2)
