"""Deliver ChatReply payloads to Telegram (shared by text and callback flows)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from telegram import Message, Update

from app.channels.telegram.keyboards import inline_keyboard_from_extra
from app.channels.telegram.messenger import TelegramMessenger
from app.domain.product_search_present import format_product_caption, product_buy_keyboard_extra
from app.infrastructure.sahiy_api.product_search import ProductSearchItem


@dataclass
class ReplyPayload:
    text: str
    reply_markup: Any = None
    photo_urls: Optional[List[str]] = None
    follow_up_messages: Optional[List[str]] = None
    product_search_items: Optional[List[Dict[str, Any]]] = None
    product_search_cny_to_uzs: Optional[float] = None
    disable_stream: bool = False

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
            product_search_items=list(channel_extra.get("product_search_items") or []) or None,
            product_search_cny_to_uzs=channel_extra.get("product_search_cny_to_uzs"),
            disable_stream=bool(channel_extra.get("disable_stream")),
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


async def deliver_product_search_cards(
    update: Update,
    messenger: TelegramMessenger,
    payload: ReplyPayload,
    *,
    lang: str,
) -> None:
    if not payload.product_search_items:
        return
    rate = float(payload.product_search_cny_to_uzs or 0.0)
    for index, raw in enumerate(payload.product_search_items, start=1):
        try:
            item = ProductSearchItem(
                title=str(raw.get("title") or ""),
                pic_url=str(raw.get("pic_url") or ""),
                detail_url=str(raw.get("detail_url") or ""),
                price_cny=float(raw.get("price_cny") or 0),
                direct_price_cny=float(raw.get("direct_price_cny") or 0),
                cargo_fee_cny=float(raw.get("cargo_fee_cny") or 0),
                sales=int(raw.get("sales") or 0),
                num_iid=raw.get("num_iid"),
            )
        except (TypeError, ValueError):
            continue
        if not item.pic_url:
            continue
        caption = format_product_caption(item, lang, cny_to_uzs=rate, index=index)
        buy_markup = inline_keyboard_from_extra(product_buy_keyboard_extra(item, lang))
        await messenger.send_product_photo(
            update,
            item.pic_url,
            caption,
            reply_markup=buy_markup,
            lang=lang,
        )


async def deliver_follow_ups_and_media(
    update: Update,
    messenger: TelegramMessenger,
    payload: ReplyPayload,
    *,
    lang: str,
) -> None:
    await deliver_product_search_cards(update, messenger, payload, lang=lang)
    for text in payload.follow_up_messages or []:
        await messenger.reply_text(update, text, lang=lang)
    if payload.photo_urls and update.message:
        await messenger.send_media_group(update, payload.photo_urls)
