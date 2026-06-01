"""Mijoz yozgan til — keyingi javoblar shu tilda (lotin / kirill / rus).

Aniqlash ustuvorligi (kirill matn uchun):
  1. O'zbek-eksklyuziv harflar (қ,ғ,ў,ҳ)      → uz_cyrl (aniq)
  2. Rus-eksklyuziv harflar   (ы,Ы,щ,Щ)        → ru     (aniq)
  3. So'z lug'ati: rus vs o'zbek scoring        → g'olib til
  4. Noaniq                                     → None   (meta/tarixdan olinadi)
"""

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

# ─── Unicode belgilari ────────────────────────────────────────────────────────

# O'zbek kirillida FAQAT ishlatiladigan harflar
_UZ_CYRL_CHARS = frozenset("қғўҳҚҒЎҲ")

# Rus kirillida FAQAT ishlatiladigan harflar (o'zbek kirillida yo'q)
# ё, э, ъ — ikkalasida ham bor, shuning uchun bu ro'yxatda YO'Q
_RU_ONLY_CHARS = frozenset("ыЫщЩ")

# ─── Rus so'z lug'ati (to'liq so'z, kirill) ──────────────────────────────────
# Faqat rus tilida mavjud yoki dominant bo'lgan so'zlar
_RU_CYRL_WORDS = frozenset({
    # Olmoshlar — shaxs
    "вы", "вас", "вам", "ваш", "ваша", "ваше", "ваши",
    "мы", "нас", "нам", "наш", "нашу", "наши",
    "они", "их", "им", "ими",
    "ты", "тебя", "тебе", "тобой",
    "я", "меня", "мне", "мной",
    # Olmoshlar — egalik (мой/твой/свой — o'zbekda yo'q)
    "мой", "мою", "моя", "моё", "мои", "моих", "моему",
    "твой", "твою", "твоя", "твоё", "твои",
    "свой", "свою", "своя", "своё", "свои",
    # Ko'rsatish olmoshlari
    "это", "этот", "эта", "эти", "этого",
    # So'roq olmoshlari
    "что", "чего", "чему", "чем",
    "где", "куда", "откуда",
    "когда", "почему", "зачем", "как",
    "который", "которая", "которые",
    # Inkor/tasdiq
    "не", "нет", "нету", "ни",
    # Modal so'zlar
    "есть", "да",
    "можно", "нужно", "надо", "нельзя",
    # Savdo/buyurtma — faqat rus grammatik shakllari (loanword ot SO'ZLARI EMAS)
    "продаёте", "продаете", "продаётся", "продается",
    "продают", "продаю", "продаёт", "продает",
    "купить", "куплю", "покупаю", "покупать",
    "заказать",
    "доставки", "доставке",
    "оплатить",
    "вернуть",
    "стоит", "стоимость",
    "сколько", "почём",
    # Salomlashish/xayrlashish
    "привет", "здравствуйте", "здравствуй", "спасибо",
    "пожалуйста", "извините", "скажите", "подскажите",
    # Boshqa rus grammatik so'zlari
    "или", "но", "если", "потому", "хочу",
    "хотел", "хотела", "хотите", "могу", "можете",
    "работает", "работаете", "бывает",
})

# Lotin (transliteratsiya) rus markerlari
_RU_LAT_STRONG = (
    "gde", "moi", "tovary", "kogda", "pochemu",
    "spasibo", "privet", "chto", "eto",
)

# ─── O'zbek kirill so'z ro'yxati ─────────────────────────────────────────────
_UZ_CYRL_HINTS = (
    "борми", "борқу",
    "келмаган", "кетилмаган", "келмади",
    "товарларим", "товарим",
    "буюртма", "буюртмам", "буюртмангиз",
    "қабул", "керак", "сотасиз", "сотилади", "сотилаяпти",
    "салом", "яхши", "ёрдам", "ёки",
    "қачон", "нима", "қаерда", "қандай",
)

# Lotin o'zbek so'z ro'yxati (kirill transliteratsiya orqali ham tekshiriladi)
_UZ_LAT_HINTS = (
    "qayerda", "qachon", "qanday", "nimani",
    "buyurtma", "buyurtmalarim",
    "orderlarim", "zakazlar",
    "rahmat", "salom", "assalom",
    "tovarim", "tovarlarim",
    "kelmagan", "kemagan",
    "bormi", "kelsa", "uchun",
    "qabul", "qilgan", "kerak",
    "rasmlari", "infosi", "sotiladi",
)

# ─── Ingliz markerlari ────────────────────────────────────────────────────────
_EN_MARKERS = (
    "where", "when", "why", "how",
    "order", "orders", "delivery", "payment", "refund",
    "hello", "thanks", "thank you", "my order",
    "track", "shipment", "available",
)

_ZH_RE = re.compile(r"[\u4e00-\u9fff]")
_CYRL_WORD_RE = re.compile(r"[а-яё]+")


def _score_cyrillic(text: str) -> tuple[int, int]:
    """(ru_score, uz_score) — kirill matn uchun xom ball."""
    low = text.lower()
    words = set(_CYRL_WORD_RE.findall(low))

    ru_score = len(words & _RU_CYRL_WORDS)

    norm = normalize_text(text)
    uz_score = sum(1 for h in _UZ_LAT_HINTS if h in norm)
    uz_score += sum(1 for h in _UZ_CYRL_HINTS if h in low)

    return ru_score, uz_score


def detect_reply_language(text: str) -> Optional[str]:
    """Joriy xabardan til aniqla; aniqlab bo'lmasa None qaytaradi.

    Qaror daraxti (kirill matn):
      1. O'zbek-eksklyuziv harflar (қ,ғ,ў,ҳ) → uz_cyrl  [yuqori ishonch]
      2. Rus-eksklyuziv harflar   (ы,Ы,щ,Щ) → ru        [yuqori ishonch]
      3. Lug'at scoring           ru > uz    → ru
                                  uz > ru    → uz_cyrl
      4. Noaniq                              → None
    """
    raw = (text or "").strip()
    if len(raw) < 2:
        return None

    if _ZH_RE.search(raw):
        return ZH

    # ── Daraja 1: O'zbek-eksklyuziv Unicode harflar ──────────────────────────
    if any(ch in raw for ch in _UZ_CYRL_CHARS):
        return UZ_CYRL

    if _has_cyrillic(raw):
        # ── Daraja 2: Rus-eksklyuziv harflar ─────────────────────────────────
        if any(ch in raw for ch in _RU_ONLY_CHARS):
            return RU

        # ── Daraja 3: Lug'at scoring ─────────────────────────────────────────
        ru_score, uz_score = _score_cyrillic(raw)

        # O'zbek so'zlari aniq topilsa — undan ustun bo'lish uchun rus
        # ko'rsatkichi o'zbekdan ANIQ kattaroq bo'lishi kerak.
        if ru_score > uz_score and ru_score > 0:
            return RU
        if uz_score > 0:
            return UZ_CYRL

        return None

    # ── Latin matn ───────────────────────────────────────────────────────────
    norm = normalize_text(raw)
    if any(m in norm for m in _RU_LAT_STRONG):
        return RU
    if any(m in norm for m in _UZ_LAT_HINTS):
        return UZ_LAT
    low = raw.lower()
    if _has_en_markers(low):
        return EN
    return None


def _has_en_markers(text: str) -> bool:
    """Ingliz markerlari — 'order' 'orderlarim' ichida substring bo'lmasin."""
    for marker in _EN_MARKERS:
        if " " in marker:
            if marker in text:
                return True
        elif re.search(rf"(?<![a-z]){re.escape(marker)}(?![a-z])", text):
            return True
    return False


def resolve_reply_language(
    text: str,
    meta: Optional[Dict[str, Any]] = None,
    recent_messages: Optional[Sequence[Message]] = None,
) -> str:
    """Til ustuvorligi:
      1. Joriy xabarda aniq til aniqlansa → o'sha til (har doim)
      2. Foydalanuvchi menuda tanlagan til (meta) → saqlanadi
      3. Oxirgi foydalanuvchi xabarlaridan aniqlash
      4. Standart: uz_lat
    """
    detected = detect_reply_language(text)
    if detected:
        return detected

    preferred = (meta or {}).get("reply_language")
    if preferred in _ALL_LANGS:
        return str(preferred)

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
        EN: (
            "I don't have exact information on this topic. "
            "You can get full details through the Sahiy app or website."
        ),
        ZH: "关于这个问题，我没有准确信息。您可以通过Sahiy应用或网站获取完整信息。",
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
        EN: (
            "Hello. I'm Sahiy assistant — write about orders, delivery, "
            "payment or returns."
        ),
        ZH: "您好，我是Sahiy助手 — 请就订单、配送、付款或退货问题留言。",
    },
    "busy": {
        UZ_LAT: "Hozir tizim band. Bir necha daqiqadan keyin qayta yozing.",
        UZ_CYRL: "Ҳозир тизим банд. Бир неча дақиқадан кейин қайта ёзинг.",
        RU: "Сейчас система занята. Напишите снова через несколько минут.",
        EN: "The system is busy right now. Please write again in a few minutes.",
        ZH: "系统目前繁忙，请几分钟后再试。",
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
        EN: (
            "Which orders would you like to see?\n"
            "Please select a button below 👇"
        ),
        ZH: "您想查看哪些订单？\n请选择下方按钮 👇",
    },
    "identity_verified_uid": {
        UZ_LAT: "✅ Hisob ID qabul qilindi. Endi savolingizni yozing.",
        UZ_CYRL: "✅ Ҳисоб ID қабул қилинди. Энди саволингизни ёзинг.",
        RU: "✅ ID аккаунта принят. Теперь напишите ваш вопрос.",
        EN: "✅ Account ID accepted. Now write your question.",
        ZH: "✅ 账户ID已确认。请提出您的问题。",
    },
    "identity_verified_phone": {
        UZ_LAT: "✅ Telefon raqamingiz tasdiqlandi. Endi savolingizni yozing.",
        UZ_CYRL: "✅ Телефон рақамингиз тасдиқланди. Энди саволингизни ёзинг.",
        RU: "✅ Номер телефона подтверждён. Теперь напишите ваш вопрос.",
        EN: "✅ Phone number confirmed. Now write your question.",
        ZH: "✅ 电话号码已确认。请提出您的问题。",
    },
    "orders_header": {
        UZ_LAT: "📋 Buyurtmalaringiz holati",
        UZ_CYRL: "📋 Буюртмаларингиз ҳолати",
        RU: "📋 Статус ваших заказов",
        EN: "📋 Your orders status",
        ZH: "📋 您的订单状态",
    },
    "orders_empty": {
        UZ_LAT: (
            "📭 Aktiv buyurtma topilmadi.\n\n"
            "Yaqinda buyurtma qilgan bo'lsangiz, birozdan keyin yozing."
        ),
        UZ_CYRL: (
            "📭 Актив буюртма топилмади.\n\n"
            "Яқинда буюртма қилган бўлсангиз, бироздан кейин ёзинг."
        ),
        RU: (
            "📭 Активных заказов не найдено.\n\n"
            "Если недавно оформляли заказ, напишите чуть позже."
        ),
        EN: (
            "📭 No active orders found.\n\n"
            "If you placed an order recently, please write again shortly."
        ),
        ZH: "📭 未找到活跃订单。\n\n如果您最近下过订单，请稍后再写。",
    },
    "orders_track_hint": {
        UZ_LAT: "Batafsil bilish uchun track raqamni yuboring.",
        UZ_CYRL: "Батафсил: track рақамни юборинг.",
        RU: "Подробнее: отправьте номер track.",
        EN: "For details, send your track number.",
        ZH: "详情：请发送tracking号码。",
    },
    "rag_greeting": {
        UZ_LAT: "Assalomu alaykum, hurmatli mijoz! ",
        UZ_CYRL: "Ассалому алайкум, ҳурматли мижоз! ",
        RU: "Здравствуйте, уважаемый клиент! ",
        EN: "Hello, dear customer! ",
        ZH: "您好，尊敬的客户！",
    },
}


def localize(key: str, lang: str) -> str:
    table = _STRINGS.get(key, {})
    return table.get(lang) or table.get(UZ_LAT, "")
