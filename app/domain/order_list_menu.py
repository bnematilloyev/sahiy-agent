"""Telegram inline tugmalar — buyurtma turini tanlash, keyin API qidiruv."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.domain.order_list_intent import OrderListIntent, parse_order_list_intent
from app.domain.order_refs import extract_track, is_order_list_question
from app.domain.text_normalize import normalize_text

CALLBACK_PREFIX = "ord"

ORDER_MENU_PROMPT = (
    "Qaysi buyurtmalaringizni ko'rsatay?\n"
    "Quyidagi tugmalardan birini tanlang 👇"
)

# callback_code -> mijoz tilidagi so'rov (parse_order_list_intent uchun)
_MENU_QUERY: Dict[str, str] = {
    "all": "buyurtmalarim holati",
    "active": "aktiv buyurtmalarim",
    "daigou": "xitoydagi daigou buyurtmalarim",
    "delivery": "yetkazib berish buyurtmalari",
    "unpicked": "olib ketilmagan buyurtmalarim",
    "cancelled": "bekor qilingan buyurtmalarim",
    "dashboard": "filialdagi buyurtmalarim",
    "completed": "yakunlangan buyurtmalarim",
}

_MENU_ROWS: Tuple[Tuple[Tuple[str, str], ...], ...] = (
    (("📋 Hammasi", "all"), ("✅ Aktiv", "active")),
    (("🇨🇳 Xitoy (daigou)", "daigou"), ("📦 Yetkazib berish", "delivery")),
    (("⏳ Olib ketilmagan", "unpicked"), ("❌ Bekor", "cancelled")),
    (("📍 Filialda", "dashboard"), ("✔️ Yakunlangan", "completed")),
)


def needs_order_list_menu(text: str) -> bool:
    """
    Aniq track/filtr yo'q — avval turini tugma bilan so'rash.
    «aktiv zakazlarim» kabi aniq so'rovda menyu chiqmaydi.
    """
    if extract_track(text):
        return False
    if not is_order_list_question(text) and not _is_vague_show_request(text):
        return False
    intent = parse_order_list_intent(text)
    return intent == OrderListIntent.default()


def _is_vague_show_request(text: str) -> bool:
    lowered = normalize_text(text or "")
    if not lowered:
        return False
    hints = (
        "zakazlarimni",
        "buyurtmalarimni",
        "zakazlarimni kor",
        "zakazlarimni ko'rsat",
        "buyurtmalarni kor",
        "buyurtmalarni ko'rsat",
        "royxat",
        "ro'yxat",
        "moi tovar",
        "moi tovary",
        "gde moi",
        "gde tovar",
    )
    return any(h in lowered for h in hints)


def build_order_list_menu_extra() -> Dict[str, Any]:
    rows: List[List[Dict[str, str]]] = []
    for row in _MENU_ROWS:
        buttons = []
        for label, code in row:
            buttons.append(
                {
                    "text": label,
                    "callback_data": f"{CALLBACK_PREFIX}_{code}",
                }
            )
        rows.append(buttons)
    return {"inline_keyboard": rows}


def parse_order_menu_callback(data: str) -> Optional[str]:
    if not data or not data.startswith(f"{CALLBACK_PREFIX}_"):
        return None
    code = data[len(CALLBACK_PREFIX) + 1 :].strip().lower()
    return _MENU_QUERY.get(code)
