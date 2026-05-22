"""Mijoz yozgan til — keyingi javoblar shu tilda (lotin / kirill / rus)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from app.domain.entities import Message
from app.domain.enums import MessageRole
from app.domain.text_normalize import _has_cyrillic, normalize_text

UZ_LAT = "uz_lat"
UZ_CYRL = "uz_cyrl"
RU = "ru"
EN = "en"
ZH = "zh"

_ALL_LANGS = (UZ_LAT, UZ_CYRL, RU, EN, ZH)

# O'zbek kirilliga xos harflar
_UZ_CYRL_CHARS = frozenset("қғўҳҚҒЎҲ")

# Rus (kirill yoki lotin)
_RU_MARKERS = (
    "где",
    "мой",
    "мои",
    "товар",
    "товары",
    "заказ",
    "когда",
    "почему",
    "спасибо",
    "привет",
    "что",
    "это",
    "или",
    "нет",
    "почему",
    "здравств",
)
_RU_LAT_STRONG = (
    "gde",
    "moi",
    "tovary",
    "kogda",
    "pochemu",
    "spasibo",
    "privet",
    "chto",
    "eto",
)
_UZ_LAT_HINTS = (
    "qayerda",
    "buyurtma",
    "zakazlar",
    "rahmat",
    "salom",
    "assalom",
    "tovarim",
    "kelsa",
    "uchun",
)
_EN_MARKERS = (
    "where",
    "when",
    "why",
    "how",
    "order",
    "orders",
    "delivery",
    "payment",
    "refund",
    "hello",
    "thanks",
    "thank you",
    "my order",
    "track",
    "shipment",
)
_ZH_RE = re.compile(r"[\u4e00-\u9fff]")


def detect_reply_language(text: str) -> Optional[str]:
    """Joriy xabardan til; aniqlanmasa None."""
    raw = (text or "").strip()
    if len(raw) < 2:
        return None

    if _ZH_RE.search(raw):
        return ZH

    if any(ch in raw for ch in _UZ_CYRL_CHARS):
        return UZ_CYRL

    if _has_cyrillic(raw):
        low = raw.lower()
        if sum(1 for m in _RU_MARKERS if m in low) >= 1:
            return RU
        return UZ_CYRL

    norm = normalize_text(raw)
    if any(m in norm for m in _RU_LAT_STRONG):
        return RU
    low = raw.lower()
    if sum(1 for m in _EN_MARKERS if m in low) >= 1:
        return EN
    if any(m in norm for m in _UZ_LAT_HINTS):
        return UZ_LAT
    return None


def resolve_reply_language(
    text: str,
    meta: Optional[Dict[str, Any]] = None,
    recent_messages: Optional[Sequence[Message]] = None,
) -> str:
    """Yangi xabar > saqlangan meta > oxirgi user xabarlar > uz_lat."""
    detected = detect_reply_language(text)
    if detected:
        return detected
    if meta and meta.get("reply_language") in _ALL_LANGS:
        return str(meta["reply_language"])
    if recent_messages:
        for msg in reversed(recent_messages):
            if msg.role != MessageRole.USER.value:
                continue
            d = detect_reply_language(msg.content)
            if d:
                return d
    return UZ_LAT


def language_instruction(lang: str) -> str:
    if lang == RU:
        return (
            "ВАЖНО: Клиент общается на русском языке. "
            "Отвечай только по-русски. Не переключайся на узбекский."
        )
    if lang == EN:
        return (
            "IMPORTANT: The customer writes in English. "
            "Reply only in English. Do not switch to Uzbek or Russian."
        )
    if lang == ZH:
        return (
            "重要：客户使用中文交流。"
            "请仅用中文回复。不要切换到乌兹别克语或俄语。"
        )
    if lang == UZ_CYRL:
        return (
            "MUHIM: Mijoz o'zbek tilida kirill alifbosida yozmoqda. "
            "Javobni faqat shu yozuvda bering (masalan: қ, ғ, ў, ҳ). Lotin va rus tilida yozma."
        )
    return (
        "MUHIM: Mijoz o'zbek tilida lotin alifbosida yozmoqda. "
        "Javobni faqat o'zbek lotin tilida bering. Rus yoki kirill yozuvda yozma."
    )


def system_prompt_with_language(base_system: str, lang: str) -> str:
    return f"{base_system.rstrip()}\n\n{language_instruction(lang)}"


# Statik matnlar (AI yo'q yo'llar)
_STRINGS: Dict[str, Dict[str, str]] = {
    "no_faq_fallback": {
        UZ_LAT: (
            "Bu savol bo'yicha aniq ma'lumotim yo'q. "
            "Sahiy ilovasi yoki veb-sayti orqali to'liq ma'lumot olishingiz mumkin."
        ),
        UZ_CYRL: (
            "Бу савол бўйича аниқ маълумотим йўқ. "
            "Sahiy иловаси ёки веб-сайти орқали тўлиқ маълумот олишингиз мумкин."
        ),
        RU: (
            "По этому вопросу у меня нет точной информации. "
            "Полные сведения можно получить в приложении Sahiy или на сайте."
        ),
    },
    "chitchat": {
        UZ_LAT: (
            "Salom. Men Sahiy yordamchisiman — buyurtma, yetkazish, "
            "to'lov yoki qaytarish bo'yicha yozing."
        ),
        UZ_CYRL: (
            "Ассалому алайкум. Мен Sahiy ёрдамчисиман — буюртма, етказиш, "
            "тўлов ёки қайтариш бўйича ёзинг."
        ),
        RU: (
            "Здравствуйте. Я помощник Sahiy — напишите по заказу, доставке, "
            "оплате или возврату."
        ),
    },
    "busy": {
        UZ_LAT: "Hozir tizim band. Bir necha daqiqadan keyin qayta yozing.",
        UZ_CYRL: "Ҳозир тизим банд. Бир неча дақиқадан кейин қайта ёзинг.",
        RU: "Сейчас система занята. Напишите снова через несколько минут.",
    },
    "order_menu_prompt": {
        UZ_LAT: (
            "Qaysi buyurtmalaringizni ko'rsatay?\n"
            "Quyidagi tugmalardan birini tanlang 👇"
        ),
        UZ_CYRL: (
            "Қайси буюртмаларингизни кўрсатай?\n"
            "Қуйидаги тугмалардан бирини танланг 👇"
        ),
        RU: (
            "Какие заказы показать?\n"
            "Выберите одну кнопку ниже 👇"
        ),
    },
    "identity_verified_uid": {
        UZ_LAT: "✅ Sahiy user ID qabul qilindi. Endi savolingizni yozing.",
        UZ_CYRL: "✅ Sahiy user ID қабул қилинди. Энди саволингизни ёзинг.",
        RU: "✅ Sahiy user ID принят. Теперь напишите ваш вопрос.",
    },
    "identity_verified_phone": {
        UZ_LAT: "✅ Telefon raqamingiz tasdiqlandi. Endi savolingizni yozing.",
        UZ_CYRL: "✅ Телефон рақамингиз тасдиқланди. Энди саволингизни ёзинг.",
        RU: "✅ Номер телефона подтверждён. Теперь напишите ваш вопрос.",
    },
    "orders_header": {
        UZ_LAT: "📋 Buyurtmalaringiz holati",
        UZ_CYRL: "📋 Буюртмаларингиз ҳолати",
        RU: "📋 Статус ваших заказов",
    },
    "orders_empty": {
        UZ_LAT: (
            "📭 Aktiv buyurtma topilmadi.\n_______\n"
            "Yaqinda buyurtma qilgan bo'lsangiz, birozdan keyin yozing."
        ),
        UZ_CYRL: (
            "📭 Актив буюртма топилмади.\n_______\n"
            "Яқинда буюртма қилган бўлсангиз, бироздан кейин ёзинг."
        ),
        RU: (
            "📭 Активных заказов не найдено.\n_______\n"
            "Если недавно оформляли заказ, напишите чуть позже."
        ),
    },
    "orders_track_hint": {
        UZ_LAT: "Batafsil: track raqam (DG... yoki TRACK...) yuboring.",
        UZ_CYRL: "Батафсил: track рақам (DG... ёки TRACK...) юборинг.",
        RU: "Подробнее: отправьте номер track (DG... или TRACK...).",
    },
    "rag_greeting": {
        UZ_LAT: "Assalomu alaykum, hurmatli mijoz! ",
        UZ_CYRL: "Ассалому алайкум, ҳурматли мижоз! ",
        RU: "Здравствуйте, уважаемый клиент! ",
    },
}


def localize(key: str, lang: str) -> str:
    table = _STRINGS.get(key, {})
    return table.get(lang) or table.get(UZ_LAT, "")
