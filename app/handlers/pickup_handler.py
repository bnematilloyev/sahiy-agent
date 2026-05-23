"""Pickup points (filial / postomat) replies for Telegram."""

from __future__ import annotations

from typing import List, Optional

from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import QuestionCategory, ResponseType
from app.domain.pickup_keywords import build_pickup_query_text
from app.domain.pickup_present import (
    build_region_keyboard,
    filter_points_by_location_query,
    format_overview,
    format_region_list,
    format_type_list,
)
from app.core.config import get_settings
from app.services.pickup_points_service import PickupPointsService


class PickupHandler:
    category = QuestionCategory.FAQ

    def __init__(self, pickup_points: Optional[PickupPointsService] = None) -> None:
        self._pickup_points = pickup_points or PickupPointsService()

    async def reply(self, context: ChatContext) -> ChatReply:
        settings = get_settings()
        if not settings.has_service_user:
            return ChatReply(
                response_type=ResponseType.AUTO,
                text="Topshirish punktlari hozircha ko'rsatilmayapti (API sozlanmagan).",
                category=self.category,
            )

        points = await self._pickup_points.fetch_points()
        if points is None:
            return ChatReply(
                response_type=ResponseType.AUTO,
                text="Topshirish punktlari vaqtincha mavjud emas.",
                category=self.category,
            )
        if not points:
            return ChatReply(
                response_type=ResponseType.AUTO,
                text="Topshirish punktlari topilmadi.",
                category=self.category,
            )

        keyboard = build_region_keyboard(points)
        query_text = build_pickup_query_text(context.text, context.recent_messages)
        local = filter_points_by_location_query(query_text, points)
        if local:
            region_name = local[0].get("region_name") or "Viloyat"
            text = format_region_list(region_name, local)
        else:
            text = format_overview(points)

        return ChatReply(
            response_type=ResponseType.AUTO,
            text=text,
            category=self.category,
            channel_extra={
                "inline_keyboard": keyboard,
                "pickup_points_count": len(points),
            },
        )

    async def reply_for_callback(self, kind: str, value: int) -> ChatReply:
        points = await self._pickup_points.fetch_points()
        if points is None:
            return ChatReply(
                response_type=ResponseType.AUTO,
                text="Topshirish punktlari vaqtincha mavjud emas.",
                category=self.category,
            )
        return self.build_callback_reply(kind, value, points)

    @staticmethod
    def build_callback_reply(kind: str, value: int, points: List[dict]) -> ChatReply:
        if kind == "t":
            filtered = [p for p in points if p.get("type") == value]
            label = "Filial punktlari" if value == 1 else "Postomatlar"
            text = format_type_list(label, filtered)
        else:
            filtered = [p for p in points if p.get("region_id") == value]
            region_name = filtered[0].get("region_name", "Viloyat") if filtered else "Viloyat"
            text = format_region_list(region_name, filtered)

        return ChatReply(
            response_type=ResponseType.AUTO,
            text=text,
            category=QuestionCategory.FAQ,
            channel_extra={"inline_keyboard": build_region_keyboard(points)},
        )
