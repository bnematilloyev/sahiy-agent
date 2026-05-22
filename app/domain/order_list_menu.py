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

# callback_code -> natural-language query (parse_order_list_intent uchun, UZ default)
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

# Localized button labels per code + lang
_MENU_LABELS: Dict[str, Dict[str, str]] = {
    "all":       {"uz_lat": "📋 Hammasi",          "uz_cyrl": "📋 Ҳаммаси",           "ru": "📋 Все",              "en": "📋 All",          "zh": "📋 全部"},
    "active":    {"uz_lat": "✅ Aktiv",             "uz_cyrl": "✅ Актив",             "ru": "✅ Активные",         "en": "✅ Active",        "zh": "✅ 活跃"},
    "daigou":    {"uz_lat": "🇨🇳 Xitoyda (xarid)",  "uz_cyrl": "🇨🇳 Хитойда (харид)", "ru": "🇨🇳 В Китае (закупка)", "en": "🇨🇳 In China (purchase)", "zh": "🇨🇳 中国（采购）"},
    "delivery":  {"uz_lat": "📦 Yetkazib berish",  "uz_cyrl": "📦 Етказиб бериш",    "ru": "📦 Доставка",         "en": "📦 Delivery",      "zh": "📦 配送"},
    "unpicked":  {"uz_lat": "⏳ Olib ketilmagan",  "uz_cyrl": "⏳ Олиб кетилмаган",  "ru": "⏳ Не получено",      "en": "⏳ Not picked up", "zh": "⏳ 待取货"},
    "cancelled": {"uz_lat": "❌ Bekor",             "uz_cyrl": "❌ Бекор",             "ru": "❌ Отменённые",       "en": "❌ Cancelled",     "zh": "❌ 已取消"},
    "dashboard": {"uz_lat": "📍 Filialda",          "uz_cyrl": "📍 Филиалда",          "ru": "📍 В филиале",        "en": "📍 At branch",     "zh": "📍 分支机构"},
    "completed": {"uz_lat": "✔️ Yakunlangan",      "uz_cyrl": "✔️ Якунланган",       "ru": "✔️ Завершённые",     "en": "✔️ Completed",    "zh": "✔️ 已完成"},
}

_MENU_CODE_ORDER: Tuple[Tuple[str, str], ...] = (
    ("all", "active"),
    ("daigou", "delivery"),
    ("unpicked", "cancelled"),
    ("dashboard", "completed"),
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
        "buyurtmalarimni ko'rmoqchiman",
        "buyurtmalarimni kormoqchiman",
        "kormoqchiman",
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


def build_order_list_menu_extra(lang: str = "uz_lat") -> Dict[str, Any]:
    rows: List[List[Dict[str, str]]] = []
    for code_pair in _MENU_CODE_ORDER:
        buttons = []
        for code in code_pair:
            labels = _MENU_LABELS.get(code, {})
            label = labels.get(lang) or labels.get("uz_lat", code)
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
