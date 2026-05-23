"""Deliver ChatReply payloads to Telegram (shared by text and callback flows)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from telegram import Message, Update

from app.channels.telegram.keyboards import inline_keyboard_from_extra
from app.channels.telegram.messenger import TelegramMessenger


@dataclass
class ReplyPayload:
    text: str
    reply_markup: Any = None
    photo_urls: Optional[List[str]] = None
    follow_up_messages: Optional[List[str]] = None

    @classmethod
    def from_channel_extra(cls, text: str, extra: Dict[str, Any]) -> "ReplyPayload":
        channel_extra = extra or {}
        return cls(
            text=text,
            reply_markup=inline_keyboard_from_extra(channel_extra),
            photo_urls=list(channel_extra.get("media_photos") or []),
            follow_up_messages=[
                str(m).strip()
                for m in (channel_extra.get("telegram_messages") or [])
                if str(m).strip()
            ],
        )


async def deliver_to_update(
    update: Update,
    messenger: TelegramMessenger,
    payload: ReplyPayload,
    *,
    lang: str,
    use_stream: bool = False,
    stream_message: Optional[Message] = None,
) -> bool:
    """Send assistant reply for a normal message update. Returns False if delivery failed."""
    if use_stream and stream_message is not None:
        display = messenger.clip_text(payload.text)
        if payload.reply_markup is not None:
            return await messenger.edit_message_text(
                stream_message,
                display,
                reply_markup=payload.reply_markup,
            )
        return await messenger.edit_message_text(stream_message, display)

    sent = await messenger.reply_text(
        update,
        payload.text,
        reply_markup=payload.reply_markup,
        lang=lang,
    )
    return sent is not None


async def deliver_follow_ups_and_media(
    update: Update,
    messenger: TelegramMessenger,
    payload: ReplyPayload,
    *,
    lang: str,
) -> None:
    for text in payload.follow_up_messages or []:
        await messenger.reply_text(update, text, lang=lang)
    if payload.photo_urls and update.message:
        await messenger.send_media_group(update, payload.photo_urls)
