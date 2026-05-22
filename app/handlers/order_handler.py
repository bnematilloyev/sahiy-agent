from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.exceptions import LLMError, LLMTimeoutError
from app.core.prompts import API_ORDER_USER_TEMPLATE, API_RESPONSE_SYSTEM
from app.domain.reply_language import UZ_LAT, system_prompt_with_language
from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import QuestionCategory, ResponseType
from app.domain.order_present import (
    collect_sku_images,
    enrich_order_summary_uzs,
    format_orders_message,
    format_sku_text,
    order_sn_from_row,
    summarize_orders_for_prompt,
)
from app.domain.order_refs import build_order_query_text, extract_track
from app.domain.verified_phone import sahiy_user_id_from_context, verified_phone_from_context
from app.infrastructure.llm.ports import AiClient
from app.infrastructure.order_api import OrderApi

logger = logging.getLogger(__name__)


class OrderHandler:
    category = QuestionCategory.API

    def __init__(self, order_api: OrderApi, ai: AiClient) -> None:
        self._orders = order_api
        self._ai = ai

    async def reply(self, context: ChatContext) -> ChatReply:
        phone = verified_phone_from_context(context)
        sahiy_uid = sahiy_user_id_from_context(context)

        query = build_order_query_text(context.text, context.recent_messages)
        lang = str(context.metadata.get("reply_language") or UZ_LAT)
        data = await self._orders.lookup(
            user_id=context.user_id,
            query=query,
            session_id=str(context.session_id),
            phone=phone,
            sahiy_user_id=sahiy_uid,
            lang=lang,
        )
        track = extract_track(query)
        if track and isinstance(data, dict):
            data["requested_track"] = track

        channel_extra: Dict[str, Any] = {}
        if (
            isinstance(data, dict)
            and data.get("order_chain")
            and not data.get("error")
            and not data.get("order_focus")
            and not data.get("daigou_focus")
            and not data.get("requested_track")
        ):
            from app.domain.order_telegram_present import build_order_telegram_messages

            messages = build_order_telegram_messages(data, lang=lang)
            text = messages[0] if messages else ""
            if len(messages) > 1:
                channel_extra["telegram_messages"] = [
                    m for m in messages[1:] if str(m).strip()
                ]
        else:
            text = await self._format_reply(data, query, reply_language=lang)

        if isinstance(data, dict) and not data.get("error"):
            sku_text, photo_urls = await self._maybe_fetch_skus(data, lang)
            if sku_text:
                text = text + "\n\n" + sku_text
            if photo_urls:
                channel_extra["media_photos"] = [u for u in photo_urls if u]

        return ChatReply(
            response_type=ResponseType.API,
            text=text,
            category=self.category,
            channel_extra=channel_extra,
        )

    async def _maybe_fetch_skus(
        self, data: dict, lang: str
    ) -> tuple[str, List[str]]:
        """Fetch SKU detail for focused single order (daigou or express track). Returns (sku_text, photo_urls)."""
        settings = get_settings()

        order_focus = data.get("order_focus")
        daigou_focus = data.get("daigou_focus")

        row: Optional[Dict[str, Any]] = None
        source = ""

        if isinstance(order_focus, dict):
            source = str(order_focus.get("source", ""))
            row = order_focus.get("row") if isinstance(order_focus.get("row"), dict) else None

        if not row and isinstance(daigou_focus, dict):
            row = daigou_focus
            source = "daigou"

        if not row:
            return "", []

        from app.domain.order_refs import is_daigou_sn
        from app.infrastructure.sahiy_api.daigou_admin import (
            DaigouOrderDetail,
            fetch_daigou_order_detail,
            find_daigou_detail_by_sn,
            parse_detail_from_row,
        )
        from app.infrastructure.sahiy_api.custom_daigou import resolve_daigou_detail
        from app.infrastructure.sahiy_api.factory import get_sahiy_api_client

        track = str(data.get("requested_track") or "").strip()
        order_sn = order_sn_from_row(row)
        if (not order_sn or order_sn == "—") and track and is_daigou_sn(track):
            order_sn = track.upper()

        user_id = data.get("user_id") or row.get("user_id")
        if not track and (not order_sn or order_sn == "—"):
            return "", []

        detail: Optional[DaigouOrderDetail] = None
        admin_tried = False

        if source == "daigou" and order_sn and settings.has_admin_api:
            admin_tried = True
            try:
                order_id = row.get("id")
                if order_id:
                    try:
                        detail = await fetch_daigou_order_detail(int(order_id))
                    except Exception:
                        pass

                if not detail and user_id:
                    detail = await find_daigou_detail_by_sn(int(user_id), order_sn)
            except Exception as exc:
                logger.warning("SKU admin fetch failed for %s: %s", order_sn, exc)

        if source == "daigou" and (not detail or not detail.skus):
            parsed = parse_detail_from_row(row)
            if parsed and parsed.skus:
                detail = parsed
                logger.info(
                    "SKU parsed from order row for %s (%d items)",
                    order_sn or track,
                    len(parsed.skus),
                )

        if (not detail or not detail.skus) and user_id and settings.has_service_user:
            client = get_sahiy_api_client()
            if client:
                try:
                    custom_detail = await resolve_daigou_detail(
                        client,
                        int(user_id),
                        track=track or None,
                        order_sn=order_sn if order_sn and order_sn != "—" else None,
                    )
                    if custom_detail and custom_detail.skus:
                        detail = custom_detail
                        logger.info(
                            "SKU from custom-daigou API for %s (%d items)",
                            track or order_sn,
                            len(custom_detail.skus),
                        )
                except Exception as exc:
                    logger.warning(
                        "SKU custom-daigou fetch failed for %s: %s",
                        track or order_sn,
                        exc,
                    )

        if not detail or not detail.skus:
            if admin_tried:
                logger.warning("No SKU for %s", track or order_sn)
            return "", []

        sku_text = format_sku_text(
            detail,
            lang,
            cny_to_uzs=await self._cny_uzs_rate(),
        )
        photo_urls: List[str] = []
        if settings.sahiy_sku_photos_enabled:
            photo_urls = collect_sku_images(detail, max_photos=5)

        return sku_text, photo_urls

    async def _cny_uzs_rate(self) -> float:
        from app.infrastructure.sahiy_api.exchange_rates import get_cny_uzs_rate

        try:
            return await get_cny_uzs_rate()
        except Exception as exc:
            logger.warning("Exchange rate fetch failed, using fallback: %s", exc)
            return get_settings().sahiy_exchange_cny_uzs_fallback

    async def _format_reply(
        self, data: dict, query: str, *, reply_language: str = UZ_LAT
    ) -> str:
        summary = summarize_orders_for_prompt(data, lang=reply_language)
        if data.get("error") or data.get("ownership_mismatch"):
            return format_orders_message(data, reply_language=reply_language)

        if data.get("order_chain"):
            from app.domain.order_telegram_present import build_order_telegram_messages

            messages = build_order_telegram_messages(data, lang=reply_language)
            return messages[0] if messages else format_orders_message(data, reply_language=reply_language)

        if summary.get("bolimlar"):
            return format_orders_message(data, reply_language=reply_language)

        if not self._ai.is_available:
            return format_orders_message(data, reply_language=reply_language)

        rate = await self._cny_uzs_rate()
        summary = enrich_order_summary_uzs(summary, rate, reply_language)
        prompt = API_ORDER_USER_TEMPLATE.format(
            query=query,
            orders_json=json.dumps(summary, ensure_ascii=False, indent=2),
        )
        try:
            return await self._ai.complete(
                system_prompt_with_language(API_RESPONSE_SYSTEM, reply_language),
                prompt,
                max_tokens=get_settings().ai_order_max_tokens,
            )
        except (LLMTimeoutError, LLMError):
            return format_orders_message(data, reply_language=reply_language)
