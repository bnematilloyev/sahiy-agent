"""Customer identification and parallel order data for RAG/API replies."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.infrastructure.sahiy_api.client import SahiyApiClient
from app.domain.order_match import (
    find_order_in_data,
    row_matches_track,
    track_focus_is_valid,
)
from app.domain.order_list_intent import (
    OrderListIntent,
    apply_list_intent_to_payload,
    parse_order_list_intent,
    should_fetch_with_list_intent,
)
from app.domain.order_refs import (
    extract_phone,
    extract_track,
    is_daigou_sn,
    is_order_list_question,
    normalize_phone,
)
from app.infrastructure.sahiy_api.daigou import fetch_daigou_orders, find_daigou_by_sn, intent_status_codes
from app.infrastructure.sahiy_api.status_maps import (
    dashboard_label,
    delivery_label,
    is_unpicked_dashboard,
)

logger = logging.getLogger(__name__)

_USER_NOT_FOUND: dict[str, str] = {
    "uz_lat": "Telefon bo'yicha mijoz topilmadi.",
    "uz_cyrl": "Телефон бўйича мижоз топилмади.",
    "ru": "Клиент с этим номером телефона не найден.",
    "en": "No customer found with this phone number.",
    "zh": "未找到该电话号码对应的客户。",
}
_IDENTIFICATION_REQUIRED: dict[str, str] = {
    "uz_lat": "Avval 📱 telefon raqamingizni yuboring (kontakt tugmasi), keyin track raqamini yozing — shunda buyurtmangiz aniq topiladi.",
    "uz_cyrl": "Аввал 📱 телефон рақамингизни юборинг (контакт тугмаси), кейин track рақамини ёзинг — шунда буюртмангиз аниқ топилади.",
    "ru": "Сначала отправьте 📱 ваш номер телефона (кнопка контакта), затем напишите номер track — и мы точно найдём ваш заказ.",
    "en": "First send 📱 your phone number (contact button), then write the track number — this way we'll find your order accurately.",
    "zh": "请先发送📱您的电话号码（联系人按钮），然后输入tracking号码——这样我们能准确找到您的订单。",
}
_OWNERSHIP_MISMATCH: dict[str, str] = {
    "uz_lat": "Bu buyurtma sizga tegishli emas.",
    "uz_cyrl": "Бу буюртма сизга тегишли эмас.",
    "ru": "Этот заказ не принадлежит вам.",
    "en": "This order does not belong to you.",
    "zh": "该订单不属于您。",
}
_ORDER_NOT_FOUND_IN_ACCOUNT: dict[str, str] = {
    "uz_lat": "Sizning buyurtmalaringizda bu raqam topilmadi.\nRaqamni tekshirib qayta yuboring.",
    "uz_cyrl": "Сизнинг буюртмаларингизда бу рақам топилмади.\nРақамни текшириб қайта юборинг.",
    "ru": "Этот номер не найден в ваших заказах.\nПроверьте номер и отправьте снова.",
    "en": "This number was not found in your orders.\nCheck the number and try again.",
    "zh": "您的订单中未找到该号码。\n请检查号码后重新发送。",
}
_ORDER_NOT_FOUND_GLOBAL: dict[str, str] = {
    "uz_lat": "Bu raqam bo'yicha buyurtma topilmadi.\nRaqamni tekshirib qayta yuboring.",
    "uz_cyrl": "Бу рақам бўйича буюртма топилмади.\nРақамни текшириб қайта юборинг.",
    "ru": "Заказ с этим номером не найден.\nПроверьте номер и отправьте снова.",
    "en": "No order found with this number.\nCheck the number and try again.",
    "zh": "未找到该号码的订单。\n请检查号码后重新发送。",
}

_TRACK_SEARCH_BY = (
    "track_number",
    "express_num",
    "tracking",
    "order_sn",
    "logistics_sn",
    "client_order_sn",
)


@dataclass
class CustomerSnapshot:
    user_id: int
    phone: Optional[str] = None
    delivery_orders: List[Dict[str, Any]] = field(default_factory=list)
    dashboard_orders: List[Dict[str, Any]] = field(default_factory=list)
    jiyun_orders: List[Dict[str, Any]] = field(default_factory=list)
    daigou_orders: List[Dict[str, Any]] = field(default_factory=list)
    daigou_total: int = 0
    daigou_focus: Optional[Dict[str, Any]] = None
    order_focus: Optional[Dict[str, Any]] = None
    tracking: Optional[Dict[str, Any]] = None
    unpicked_delivery: List[Dict[str, Any]] = field(default_factory=list)
    ownership_mismatch: bool = False
    requested_track: Optional[str] = None
    list_scope: Optional[str] = None
    order_chain: Optional[List[Dict[str, Any]]] = None
    use_order_chain: bool = False

    def to_api_payload(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "phone": self.phone,
            "delivery_orders": self.delivery_orders,
            "dashboard_orders": self.dashboard_orders,
            "jiyun_orders": self.jiyun_orders,
            "daigou_orders": self.daigou_orders,
            "daigou_total": self.daigou_total,
            "daigou_focus": self.daigou_focus,
            "order_focus": self.order_focus,
            "tracking": self.tracking,
            "unpicked_delivery": self.unpicked_delivery,
            "ownership_mismatch": self.ownership_mismatch,
            "requested_track": self.requested_track,
            "list_scope": self.list_scope,
            "order_chain": self.order_chain,
            "use_order_chain": self.use_order_chain,
            "status_labels": {
                "delivery": delivery_label,
                "dashboard": dashboard_label,
            },
        }


class CustomerApi:
    def __init__(self, client: SahiyApiClient) -> None:
        self._client = client

    async def lookup(
        self,
        *,
        verified_user_id: Optional[int] = None,
        phone: Optional[str] = None,
        query: str = "",
        track_number: Optional[str] = None,
        lang: str = "uz_lat",
    ) -> CustomerSnapshot | Dict[str, str]:
        track = track_number or extract_track(query)
        normalized_phone = normalize_phone(phone) if phone else extract_phone(query)

        user_id: Optional[int] = None
        if verified_user_id is not None:
            user_id = verified_user_id
            logger.info("Sahiy identify by cached sahiy_user_id=%s", user_id)
        elif normalized_phone:
            user_id = await self.find_user_id_by_phone(normalized_phone)
            logger.info(
                "Sahiy identify by phone=%s -> user_id=%s",
                normalized_phone,
                user_id,
            )
            if user_id is None:
                return {
                    "error": "user_not_found",
                    "message": _USER_NOT_FOUND.get(lang, _USER_NOT_FOUND["uz_lat"]),
                }

        if user_id is None and track:
            logger.info("Sahiy track lookup start track=%r (no phone/user_id)", track)
            tracking = await self.get_tracking(track)
            owner_id = await self.resolve_user_id_for_track(track, tracking)
            if owner_id is None:
                _id_msg = _IDENTIFICATION_REQUIRED.get(lang, _IDENTIFICATION_REQUIRED["uz_lat"])
                return {
                    "error": "identification_required",
                    "message": f"🔎 {track}\n_______\n{_id_msg}",
                }
            if verified_user_id is not None and owner_id != verified_user_id:
                return self._ownership_mismatch_error(track, lang=lang)
            snapshot = await self.build_snapshot(owner_id, phone=normalized_phone)
            if tracking:
                snapshot.tracking = tracking
            focused = await self._apply_track_focus(snapshot, track, lang=lang)
            if isinstance(focused, dict):
                return focused
            return snapshot

        if user_id is None:
            _id_msg2 = {
                "uz_lat": "Telefon yoki track raqamini yuboring.",
                "uz_cyrl": "Телефон ёки track рақамини юборинг.",
                "ru": "Отправьте номер телефона или номер track.",
                "en": "Please send your phone number or track number.",
                "zh": "请发送您的电话号码或tracking号码。",
            }
            return {
                "error": "identification_required",
                "message": _id_msg2.get(lang, _id_msg2["uz_lat"]),
            }

        list_intent: Optional[OrderListIntent] = None
        if should_fetch_with_list_intent(query, track=track):
            list_intent = parse_order_list_intent(query)

        snapshot = await self.build_snapshot(
            user_id,
            phone=normalized_phone,
            intent=list_intent,
        )
        if list_intent is not None:
            payload = apply_list_intent_to_payload(snapshot.to_api_payload(), list_intent, lang)
            snapshot = self._snapshot_from_filtered_payload(snapshot, payload, list_intent, lang)

        if track and not is_order_list_question(query):
            focused = await self._apply_track_focus(snapshot, track, lang=lang)
            if isinstance(focused, dict):
                return focused
            return await self._finalize_track_lookup(focused, track, user_id=user_id, lang=lang)
        return snapshot

    async def _finalize_track_lookup(
        self,
        snapshot: CustomerSnapshot,
        track: str,
        *,
        user_id: int,
        lang: str = "uz_lat",
    ) -> CustomerSnapshot | Dict[str, str]:
        """Never return a full list when a specific track was requested."""
        snapshot.requested_track = track
        if track_focus_is_valid(snapshot, track):
            return snapshot

        snapshot.order_focus = None
        snapshot.daigou_focus = None
        snapshot.tracking = None

        owner_id = await self.resolve_user_id_for_track(track)
        if owner_id is not None and owner_id != user_id:
            logger.info(
                "Track %r owner_id=%s != verified user_id=%s -> ownership_mismatch",
                track,
                owner_id,
                user_id,
            )
            return self._ownership_mismatch_error(track, lang=lang)
        if owner_id is not None:
            return self._order_not_found_error(track, in_account=True, lang=lang)
        return self._order_not_found_error(track, in_account=False, lang=lang)

    async def _apply_track_focus(
        self, snapshot: CustomerSnapshot, track: str, lang: str = "uz_lat"
    ) -> CustomerSnapshot | Dict[str, str]:
        """Find track in user's orders; return focused snapshot or error (not full list)."""
        payload = snapshot.to_api_payload()
        match = find_order_in_data(payload, track)
        if match:
            snapshot.order_focus = match
            logger.info(
                "Track %r found in snapshot user_id=%s source=%s",
                track,
                snapshot.user_id,
                match.get("source"),
            )
            return snapshot

        if is_daigou_sn(track):
            settings = get_settings()
            focus = await find_daigou_by_sn(
                self._client,
                snapshot.user_id,
                track,
                max_pages=settings.sahiy_daigou_max_pages_search,
            )
            if focus is None:
                return self._order_not_found_error(track, in_account=True, lang=lang)
            snapshot.daigou_focus = focus
            snapshot.order_focus = {"source": "daigou", "row": focus}
            sns = {str(r.get("order_sn", "")).upper() for r in snapshot.daigou_orders}
            if focus.get("order_sn", "").upper() not in sns:
                snapshot.daigou_orders = [focus, *snapshot.daigou_orders]
            return snapshot

        extra = await self._find_delivery_row(snapshot.user_id, track)
        if extra:
            snapshot.order_focus = {"source": "delivery", "row": extra}
            return snapshot

        jiyun = await self._find_jiyun_row(snapshot.user_id, track)
        if jiyun:
            snapshot.order_focus = {"source": "jiyun", "row": jiyun}
            return snapshot

        tracking = await self.get_tracking(track)
        if tracking and row_matches_track(tracking, track):
            owner_id = _extract_user_id(tracking)
            if owner_id is not None and owner_id != snapshot.user_id:
                return self._ownership_mismatch_error(track, lang=lang)
            snapshot.tracking = tracking
            snapshot.order_focus = {"source": "tracking", "row": tracking}
            return snapshot
        if tracking:
            logger.warning(
                "Tracking API returned payload for %r but track fields do not match",
                track,
            )

        owner_id = await self.resolve_user_id_for_track(track, tracking if tracking else None)
        if owner_id is not None and owner_id != snapshot.user_id:
            return self._ownership_mismatch_error(track, lang=lang)
        if owner_id is not None:
            return self._order_not_found_error(track, in_account=True, lang=lang)
        return self._order_not_found_error(track, in_account=False, lang=lang)

    async def _find_jiyun_row(self, user_id: int, track: str) -> Optional[Dict[str, Any]]:
        body = await self._client.get_json("/api/custom/orders", params={"user": user_id})
        rows = _extract_list(body, keys=("data", "orders", "items"))
        for row in rows:
            if isinstance(row, dict) and row_matches_track(row, track):
                logger.info("Track %r found in jiyun orders user_id=%s", track, user_id)
                return row
        return None

    async def _find_delivery_row(self, user_id: int, track: str) -> Optional[Dict[str, Any]]:
        """Scan delivery list (multiple pages) when track not in first snapshot page."""
        settings = get_settings()
        page = 1
        max_pages = max(2, settings.sahiy_daigou_max_pages_search)
        while page <= max_pages:
            body = await self._client.get_json(
                f"/api/v2/admin/delivery/orders/user/{user_id}",
                params={"page": page} if page > 1 else None,
            )
            rows = _extract_list(body, keys=("data", "orders", "items"))
            for row in rows:
                if isinstance(row, dict) and row_matches_track(row, track):
                    return row
            if not rows or len(rows) < 20:
                break
            page += 1
        return None

    @staticmethod
    def _ownership_mismatch_error(track: str, lang: str = "uz_lat") -> Dict[str, str]:
        _msg = _OWNERSHIP_MISMATCH.get(lang, _OWNERSHIP_MISMATCH["uz_lat"])
        return {
            "error": "ownership_mismatch",
            "ownership_mismatch": True,
            "message": f"🔎 {track}\n_______\n{_msg}",
        }

    @staticmethod
    def _order_not_found_error(track: str, *, in_account: bool, lang: str = "uz_lat") -> Dict[str, str]:
        if in_account:
            _msg = _ORDER_NOT_FOUND_IN_ACCOUNT.get(lang, _ORDER_NOT_FOUND_IN_ACCOUNT["uz_lat"])
        else:
            _msg = _ORDER_NOT_FOUND_GLOBAL.get(lang, _ORDER_NOT_FOUND_GLOBAL["uz_lat"])
        return {"error": "order_not_found", "message": f"🔎 {track}\n_______\n{_msg}"}

    async def find_user_id_by_phone(self, phone: str) -> Optional[int]:
        path = "/api/v2/admin/delivery/orders/search"
        params = {"search_by": "phone", "query": phone}
        logger.info("Sahiy API GET %s params=%s", path, params)
        body = await self._client.get_json(path, params=params)
        return _first_user_id(body)

    async def find_user_id_by_search(self, query: str) -> Optional[int]:
        path = "/api/v2/admin/delivery/orders/search"
        for search_by in _TRACK_SEARCH_BY:
            params = {"search_by": search_by, "query": query}
            logger.info("Sahiy API GET %s params=%s", path, params)
            body = await self._client.get_json(path, params=params)
            uid = _first_user_id(body)
            if uid is not None:
                logger.info("Sahiy search %s=%r -> user_id=%s", search_by, query, uid)
                return uid
        return None

    async def get_tracking(self, track_number: str) -> Optional[Dict[str, Any]]:
        path = f"/api/v2/admin/delivery/orders/tracking/{track_number.strip()}"
        logger.info("Sahiy API GET %s", path)
        body = await self._client.get_json(path)
        if isinstance(body, dict) and body:
            return body
        return None

    async def resolve_user_id_for_track(
        self,
        track: str,
        tracking: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        if tracking is None:
            tracking = await self.get_tracking(track)
        if tracking and row_matches_track(tracking, track):
            owner_id = _extract_user_id(tracking)
            if owner_id is not None:
                logger.info("Sahiy track %r -> user_id=%s (tracking API)", track, owner_id)
                return owner_id
            logger.warning(
                "Tracking API %r: user_id topilmadi, search fallback",
                track,
            )
        elif tracking:
            logger.warning(
                "Tracking API %r: payload does not match track, search fallback",
                track,
            )
        owner_id = await self.find_user_id_by_search(track)
        if owner_id is not None:
            return owner_id
        if is_daigou_sn(track):
            compact = re.sub(r"[\s-]", "", track.upper())
            if compact != track:
                return await self.find_user_id_by_search(compact)
        return None

    @staticmethod
    def _snapshot_from_filtered_payload(
        base: CustomerSnapshot,
        payload: Dict[str, Any],
        intent: OrderListIntent,
        lang: str = "uz_lat",
    ) -> CustomerSnapshot:
        return CustomerSnapshot(
            user_id=base.user_id,
            phone=base.phone,
            delivery_orders=list(payload.get("delivery_orders") or []),
            dashboard_orders=list(payload.get("dashboard_orders") or []),
            jiyun_orders=list(payload.get("jiyun_orders") or []),
            daigou_orders=list(payload.get("daigou_orders") or []),
            daigou_total=int(payload.get("daigou_total") or 0),
            daigou_focus=base.daigou_focus,
            order_focus=base.order_focus,
            tracking=base.tracking,
            unpicked_delivery=list(payload.get("unpicked_delivery") or []),
            ownership_mismatch=base.ownership_mismatch,
            requested_track=base.requested_track,
            list_scope=payload.get("list_scope") or intent.scope_title(lang),
            order_chain=payload.get("order_chain"),
            use_order_chain=bool(payload.get("use_order_chain")),
        )

    async def build_snapshot(
        self,
        user_id: int,
        *,
        phone: Optional[str] = None,
        intent: Optional[OrderListIntent] = None,
    ) -> CustomerSnapshot:
        from app.domain.order_chain import enrichment_sources, should_use_order_chain

        base_intent = intent if intent is not None else OrderListIntent.default()
        fetch = set(base_intent.sources)
        if should_use_order_chain(base_intent):
            fetch |= set(enrichment_sources())

        task_map: Dict[str, Any] = {}
        if "delivery" in fetch:
            task_map["delivery"] = self._delivery_orders(user_id)
        if "dashboard" in fetch:
            task_map["dashboard"] = self._dashboard_orders(user_id)
        if "jiyun" in fetch:
            task_map["jiyun"] = self._jiyun_orders(user_id)
        if "daigou" in fetch:
            task_map["daigou"] = self._daigou_orders(
                user_id,
                row_filter=base_intent.row_filter if intent is not None else None,
            )
        if "unpicked" in fetch:
            task_map["unpicked"] = self._unpicked_delivery(user_id)

        keys = list(task_map.keys())
        results = (
            await asyncio.gather(*task_map.values(), return_exceptions=True)
            if keys
            else []
        )
        by_src = dict(zip(keys, results))

        def _unwrap_list(result: Any, label: str) -> list:
            if isinstance(result, Exception):
                logger.warning("Customer API %s failed: %s", label, result)
                return []
            return result if isinstance(result, list) else []

        def _unwrap_daigou(result: Any) -> tuple[list, int]:
            if isinstance(result, Exception):
                logger.warning("Customer API daigou failed: %s", result)
                return [], 0
            if isinstance(result, tuple) and len(result) == 2:
                items, total = result
                return (items if isinstance(items, list) else []), int(total or 0)
            return [], 0

        dg_items, dg_total = _unwrap_daigou(by_src.get("daigou", ([], 0)))

        return CustomerSnapshot(
            user_id=user_id,
            phone=phone,
            delivery_orders=_unwrap_list(by_src.get("delivery", []), "delivery"),
            dashboard_orders=_unwrap_list(by_src.get("dashboard", []), "dashboard"),
            jiyun_orders=_unwrap_list(by_src.get("jiyun", []), "jiyun"),
            daigou_orders=dg_items,
            daigou_total=dg_total,
            unpicked_delivery=_unwrap_list(by_src.get("unpicked", []), "unpicked"),
        )

    async def _delivery_orders(self, user_id: int) -> List[Dict[str, Any]]:
        body = await self._client.get_json(f"/api/v2/admin/delivery/orders/user/{user_id}")
        return _extract_list(body, keys=("data", "orders", "items"))

    async def _dashboard_orders(self, user_id: int) -> List[Dict[str, Any]]:
        body = await self._client.get_json(f"/api/client/dashboard/show/{user_id}")
        return _extract_list(body, keys=("data", "orders", "items"))

    async def _jiyun_orders(self, user_id: int) -> List[Dict[str, Any]]:
        body = await self._client.get_json("/api/custom/orders", params={"user": user_id})
        return _extract_list(body, keys=("data", "orders", "items"))

    async def _daigou_orders(
        self,
        user_id: int,
        *,
        row_filter: Optional[str] = None,
    ) -> tuple[List[Dict[str, Any]], int]:
        settings = get_settings()
        status_codes = intent_status_codes(row_filter)
        items, total = await fetch_daigou_orders(
            self._client,
            user_id,
            page=1,
            size=settings.sahiy_daigou_page_size,
            status_codes=status_codes,
        )
        logger.info(
            "Daigou fetch user_id=%s row_filter=%r status_codes=%s → %d items",
            user_id,
            row_filter,
            status_codes,
            len(items),
        )
        return items, total

    async def _unpicked_delivery(self, user_id: int) -> List[Dict[str, Any]]:
        body = await self._client.get_json(
            "/api/v2/admin/delivery/orders/filter",
            params_list=[
                ("user_id", user_id),
                ("delivered", "false"),
                ("with[]", "user"),
                ("with[]", "location.branch"),
            ],
        )
        items = _extract_list(body, keys=("data", "orders", "items"))
        enriched: List[Dict[str, Any]] = []
        for row in items:
            if not isinstance(row, dict):
                continue
            status = _coerce_int(row.get("status"))
            dash_status = _coerce_int(row.get("dashboard_status"))
            row = {
                **row,
                "status_label": delivery_label(status),
                "possibly_delayed": status == 4,
                "dashboard_unpicked": is_unpicked_dashboard(dash_status),
            }
            enriched.append(row)
        return enriched


def _coerce_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _extract_user_id(payload: Any, *, _depth: int = 0) -> Optional[int]:
    if _depth > 8 or payload is None:
        return None
    if isinstance(payload, dict):
        for key in ("user_id", "userId", "customer_id", "customerId"):
            if key in payload:
                uid = _coerce_int(payload[key])
                if uid is not None:
                    return uid
        for key in (
            "user",
            "customer",
            "order",
            "delivery_order",
            "deliveryOrder",
            "data",
            "result",
            "order_info",
        ):
            if key in payload:
                uid = _extract_user_id(payload[key], _depth=_depth + 1)
                if uid is not None:
                    return uid
        return None
    if isinstance(payload, list):
        for item in payload[:8]:
            uid = _extract_user_id(item, _depth=_depth + 1)
            if uid is not None:
                return uid
    return None


def _first_user_id(body: Any) -> Optional[int]:
    if isinstance(body, dict):
        uid = _extract_user_id(body)
        if uid is not None:
            return uid
        for key in ("order", "delivery_order", "data"):
            nested = body.get(key)
            if isinstance(nested, dict):
                uid = _extract_user_id(nested)
                if uid is not None:
                    return uid
    items = _extract_list(body, keys=("data", "orders", "items", "results"))
    for row in items:
        if not isinstance(row, dict):
            continue
        uid = _extract_user_id(row) or _coerce_int(row.get("user_id"))
        if uid is not None:
            return uid
    return None


def _extract_list(body: Any, *, keys: tuple[str, ...]) -> List[Dict[str, Any]]:
    if body is None:
        return []
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if not isinstance(body, dict):
        return []
    for key in keys:
        chunk = body.get(key)
        if isinstance(chunk, list):
            return [x for x in chunk if isinstance(x, dict)]
        if isinstance(chunk, dict):
            nested = _extract_list(chunk, keys=keys)
            if nested:
                return nested
    return []
