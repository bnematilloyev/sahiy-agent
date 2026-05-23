"""Telegram asosiy menyu tugmalari va xizmat baholash."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.domain.reply_language import EN, RU, UZ_CYRL, UZ_LAT, ZH

RATING_CALLBACK_PREFIX = "rate"

# action_key -> label per language
_MAIN_MENU: Dict[str, Dict[str, str]] = {
    UZ_LAT: {
        "callback": "📞 Qayta qo'ng'iroq",
        "new_chat": "🔄 Yangi suhbat",
        "language": "🌐 Tilni o'zgartirish",
        "help": "❓ Yordam",
        "product_search": "🔍 Mahsulot qidirish",
    },
    UZ_CYRL: {
        "callback": "📞 Қайта қўнғироқ",
        "new_chat": "🔄 Янги суҳбат",
        "language": "🌐 Тилни ўзгартириш",
        "help": "❓ Ёрдам",
        "product_search": "🔍 Маҳсулот қидириш",
    },
    RU: {
        "callback": "📞 Обратный звонок",
        "new_chat": "🔄 Новый чат",
        "language": "🌐 Сменить язык",
        "help": "❓ Помощь",
        "product_search": "🔍 Поиск товаров",
    },
    EN: {
        "callback": "📞 Request a call",
        "new_chat": "🔄 New chat",
        "language": "🌐 Change language",
        "help": "❓ Help",
        "product_search": "🔍 Search products",
    },
    ZH: {
        "callback": "📞 回电请求",
        "new_chat": "🔄 新对话",
        "language": "🌐 更改语言",
        "help": "❓ 帮助",
        "product_search": "🔍 搜索商品",
    },
}

PRODUCT_SEARCH_PROMPT: Dict[str, str] = {
    UZ_LAT: "Mahsulot nomini yozing (masalan: kiyim, telefon, sumka)...",
    UZ_CYRL: "Маҳсулот номини ёзинг (масалан: кийим, телефон, сумка)...",
    RU: "Введите название товара (например: одежда, телефон, сумка)...",
    EN: "Enter a product name (e.g. clothing, phone, bag)...",
    ZH: "请输入商品名称（例如：服装、手机、包）...",
}

PRODUCT_SEARCH_EMPTY: Dict[str, str] = {
    UZ_LAT: "Hech narsa topilmadi. Boshqa nom bilan qidirib ko'ring.",
    UZ_CYRL: "Ҳеч нарса топилмади. Бошқа ном билан қидириб кўринг.",
    RU: "Ничего не найдено. Попробуйте другое название.",
    EN: "Nothing found. Try a different keyword.",
    ZH: "未找到结果。请尝试其他关键词。",
}

PRODUCT_SEARCH_ERROR: Dict[str, str] = {
    UZ_LAT: "Qidiruv vaqtincha ishlamayapti. Birozdan keyin urinib ko'ring.",
    UZ_CYRL: "Қидирув вақтинча ишламайапти. Бироздан кейин уриниб кўринг.",
    RU: "Поиск временно недоступен. Попробуйте позже.",
    EN: "Search is temporarily unavailable. Please try again later.",
    ZH: "搜索暂时不可用，请稍后再试。",
}

PRODUCT_SEARCH_TOO_SHORT: Dict[str, str] = {
    UZ_LAT: "Kamida 2 ta harf yozing.",
    UZ_CYRL: "Камida 2 та ҳарф ёзинг.",
    RU: "Введите минимум 2 символа.",
    EN: "Enter at least 2 characters.",
    ZH: "请至少输入2个字符。",
}

PRODUCT_SEARCH_HEADER: Dict[str, str] = {
    UZ_LAT: "🔍 «{keyword}» bo'yicha topildi ({count} ta):",
    UZ_CYRL: "🔍 «{keyword}» бўйича топилди ({count} та):",
    RU: "🔍 По запросу «{keyword}» найдено ({count}):",
    EN: "🔍 Results for «{keyword}» ({count}):",
    ZH: "🔍 「{keyword}」的搜索结果（{count}）：",
}

RATING_PROMPT: Dict[str, str] = {
    UZ_LAT: "Xizmatimizni baholang:",
    UZ_CYRL: "Хизматимизни баҳоланг:",
    RU: "Оцените наш сервис:",
    EN: "Rate our service:",
    ZH: "请为我们的服务评分：",
}

RATING_THANKS: Dict[str, str] = {
    UZ_LAT: "Rahmat! Bahoingiz qabul qilindi ({stars}/5).",
    UZ_CYRL: "Рахмат! Баҳоингиз қабул қилинди ({stars}/5).",
    RU: "Спасибо! Ваша оценка принята ({stars}/5).",
    EN: "Thank you! Your rating ({stars}/5) has been recorded.",
    ZH: "谢谢！已记录您的评分（{stars}/5）。",
}

MENU_HELP: Dict[str, str] = {
    UZ_LAT: (
        "Men Sahiy yordamchisiman — buyurtma, yetkazish, to'lov va qaytarish bo'yicha yordam beraman.\n\n"
        "• Buyurtmalar — «Buyurtmalarimni ko'rmoqchiman» deb yozing\n"
        "• Track — DG yoki raqam yuboring\n"
        "• Mahsulot qidirish — pastdagi tugma, keyin nom yozing\n"
        "• Operator — @sahiy_operator\n\n"
        "Pastdagi tugmalardan ham foydalanishingiz mumkin."
    ),
    UZ_CYRL: (
        "Мен Sahiy ёрдамчисиман — буюртма, етказиш, тўлов ва қайтариш бўйича ёрдам бераман.\n\n"
        "• Буюртмалар — «Буюртмаларимни кўрмоқчиман» деб ёзинг\n"
        "• Track — DG ёки рақам юборинг\n"
        "• Оператор — @sahiy_operator"
    ),
    RU: (
        "Я помощник Sahiy — заказы, доставка, оплата и возвраты.\n\n"
        "• Заказы — напишите «Хочу посмотреть мои заказы»\n"
        "• Track — отправьте DG или номер\n"
        "• Оператор — @sahiy_operator"
    ),
    EN: (
        "I'm the Sahiy assistant — orders, delivery, payment, and returns.\n\n"
        "• Orders — write «I want to see my orders»\n"
        "• Track — send a DG or tracking number\n"
        "• Operator — @sahiy_operator"
    ),
    ZH: (
        "我是Sahiy助理——订单、配送、付款和退货。\n\n"
        "• 订单 — 输入「我想查看我的订单」\n"
        "• Track — 发送DG或tracking号码\n"
        "• 客服 — @sahiy_operator"
    ),
}

MENU_CALLBACK: Dict[str, str] = {
    UZ_LAT: (
        "Operator siz bilan bog'lanishi uchun @sahiy_operator ga yozing "
        "yoki telefon raqamingizni qoldiring — imkon qadar tez qo'ng'iroq qilamiz."
    ),
    UZ_CYRL: (
        "Оператор билан боғланиш учун @sahiy_operator га ёзинг "
        "ёки телефон рақамингизни қолдиринг — имкон қадар тез қўнғироқ қиламиз."
    ),
    RU: (
        "Чтобы оператор связался с вами, напишите @sahiy_operator "
        "или оставьте номер телефона — перезвоним как можно скорее."
    ),
    EN: (
        "For a callback, message @sahiy_operator "
        "or leave your phone number — we will call you back as soon as we can."
    ),
    ZH: "如需回电，请联系 @sahiy_operator 或留下您的电话号码。",
}


def _labels_for_lang(lang: str) -> Dict[str, str]:
    return _MAIN_MENU.get(lang) or _MAIN_MENU[UZ_LAT]


def main_menu_button_texts(lang: str = UZ_LAT) -> Dict[str, str]:
    return dict(_labels_for_lang(lang))


def is_main_menu_label(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    for labels in _MAIN_MENU.values():
        if stripped in labels.values():
            return True
    return False


def match_menu_action(text: str, lang: str = UZ_LAT) -> Optional[str]:
    """Matnni menyu action kalitiga map qiladi (callback, new_chat, language, help)."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    preferred = _labels_for_lang(lang)
    for key, label in preferred.items():
        if stripped == label:
            return key
    for labels in _MAIN_MENU.values():
        for key, label in labels.items():
            if stripped == label:
                return key
    return None


def build_rating_inline_extra() -> Dict[str, Any]:
    row: List[Dict[str, str]] = [
        {"text": f"⭐ {n}", "callback_data": f"{RATING_CALLBACK_PREFIX}_{n}"}
        for n in range(1, 6)
    ]
    return {"inline_keyboard": [row]}


def parse_rating_callback(data: str) -> Optional[int]:
    if not data or not data.startswith(f"{RATING_CALLBACK_PREFIX}_"):
        return None
    suffix = data[len(RATING_CALLBACK_PREFIX) + 1 :].strip()
    if suffix.isdigit():
        stars = int(suffix)
        if 1 <= stars <= 5:
            return stars
    return None


def localize_menu(table: Dict[str, str], lang: str, **kwargs: str) -> str:
    text = table.get(lang) or table.get(UZ_LAT, "")
    if kwargs:
        return text.format(**kwargs)
    return text
