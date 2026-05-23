"""Telegram-only copy tables (channel presentation layer)."""

from __future__ import annotations

WELCOME: dict[str, str] = {
    "uz_lat": (
        "Assalomu alaykum! Men Sahiy platformasining yordamchi botiman.\n"
        "\n"
        "Davom etish uchun hisobingiz ID raqamini yoki telefon raqamingizni yuboring:\n"
        "• ID — masalan: 111111\n"
        "• telefon — quyidagi tugma yoki 998901234567\n"
        "\n"
        "Buyurtmalar: «Buyurtmalarimni ko'rmoqchiman» deb yozing — turini tugmalar orqali tanlaysiz.\n"
        "Topshirish punktlari: «Filial» yoki «Postomat» deb yozing.\n"
        "\n"
        "Yangi suhbat boshlash: /new"
    ),
    "uz_cyrl": (
        "Ассалому алайкум! Мен Sahiy платформасининг ёрдамчи ботман.\n"
        "\n"
        "Давом этиш учун ҳисобингиз ID рақамини ёки телефон рақамингизни юборинг:\n"
        "• ID — масалан: 111111\n"
        "• телефон — «Телефон рақамни юбориш» тугмаси ёки 998901234567\n"
        "\n"
        "Буюртмалар: «Буюртмаларимни кўрмоқчиман» деб ёзинг — турини тугмалар орқали танлайсиз.\n"
        "Топшириш пунктлари: «Филиал» ёки «Постомат» деб ёзинг.\n"
        "\n"
        "Янги суҳбат бошлаш: /new"
    ),
    "ru": (
        "Здравствуйте! Я помощник платформы Sahiy.\n"
        "\n"
        "Для продолжения отправьте ID вашего аккаунта или номер телефона:\n"
        "• ID — например: 111111\n"
        "• телефон — кнопка ниже или 998901234567\n"
        "\n"
        "Заказы: напишите «Хочу посмотреть мои заказы» — тип выберите кнопкой.\n"
        "Пункты выдачи: напишите «Филиал» или «Постомат».\n"
        "\n"
        "Начать новый диалог: /new"
    ),
    "en": (
        "Hello! I'm the Sahiy assistant bot.\n"
        "\n"
        "To continue, send your account ID or phone number:\n"
        "• ID — e.g. 111111\n"
        "• phone — use the button below or 998901234567\n"
        "\n"
        "Orders: write «I want to see my orders» — then pick a type using the buttons.\n"
        "Pickup points: write «Branch» or «Pickup locker».\n"
        "\n"
        "Start a new chat: /new"
    ),
    "zh": (
        "您好！我是Sahiy平台助理机器人。\n"
        "\n"
        "请发送您的账户ID或电话号码以继续：\n"
        "• ID — 例如：111111\n"
        "• 电话 — 点击下方按钮或发送 998901234567\n"
        "\n"
        "订单：输入「我想查看我的订单」— 然后通过按钮选择类型。\n"
        "取货点：输入「分支机构」或「自取柜」。\n"
        "\n"
        "开始新对话：/new"
    ),
}

PHONE_SAVED: dict[str, str] = {
    "uz_lat": "Rahmat! Telefon raqamingiz saqlandi. Endi savolingizni yozing.",
    "uz_cyrl": "Раҳмат! Телефон рақамингиз сақланди. Энди саволингизни ёзинг.",
    "ru": "Спасибо! Номер телефона сохранён. Теперь напишите ваш вопрос.",
    "en": "Thank you! Your phone number has been saved. Now write your question.",
    "zh": "谢谢！您的电话号码已保存。请提出您的问题。",
}

PHONE_PROMPT: dict[str, str] = {
    "uz_lat": (
        "Hisob ID raqamingizni (masalan: 111111) yoki telefon raqamingizni yuboring — "
        "«Telefon raqamni yuborish» tugmasidan ham foydalanishingiz mumkin."
    ),
    "uz_cyrl": (
        "Ҳисоб ID рақамингизни (масалан: 111111) ёки телефон рақамингизни юборинг — "
        "«Телефон рақамни юбориш» тугмасидан хам фойдаланишинг мумкин."
    ),
    "ru": (
        "Отправьте ID аккаунта (например: 111111) или номер телефона — "
        "также можно нажать «Отправить номер телефона»."
    ),
    "en": (
        "Send your account ID (e.g. 111111) or phone number — "
        "you can also tap «Send phone number»."
    ),
    "zh": "请发送账户ID（例如：111111）或电话号码 — 也可点击«发送电话号码»按钮。",
}

PHONE_SAVED: dict[str, str] = {
    "uz_lat": "Rahmat! Telefon raqamingiz saqlandi. Endi savolingizni yozing.",
    "uz_cyrl": "Раҳмат! Телефон рақамингиз сақланди. Энди саволингизни ёзинг.",
    "ru": "Спасибо! Номер телефона сохранён. Теперь напишите ваш вопрос.",
    "en": "Thank you! Your phone number has been saved. Now write your question.",
    "zh": "谢谢！您的电话号码已保存。请提出您的问题。",
}

PHONE_WRONG_CONTACT: dict[str, str] = {
    "uz_lat": (
        "Telefon raqamini aniqlab bo'lmadi.\n\n"
        "Hisob ID raqamingizni yozing (masalan: 111111) yoki "
        "«Telefon raqamni yuborish» tugmasini bosing."
    ),
    "uz_cyrl": (
        "Телефон рақамини аниқлаб бўлмади.\n\n"
        "Ҳисоб ID рақамингизни ёзинг (масалан: 111111) ёки "
        "«Телефон рақамни юбориш» тугмасини босинг."
    ),
    "ru": (
        "Не удалось определить номер телефона.\n\n"
        "Напишите ID аккаунта (например: 111111) или нажмите «Отправить номер телефона»."
    ),
    "en": (
        "Could not determine phone number.\n\n"
        "Write your account ID (e.g. 111111) or press «Send phone number»."
    ),
    "zh": "无法确认电话号码。\n\n请输入账户ID（例如：111111）或点击«发送电话号码»。",
}

FALLBACK_ERROR: dict[str, str] = {
    "uz_lat": "Hozir javob yubora olmadim (tarmoq xatosi). Iltimos, 1–2 daqiqadan keyin qayta yozing.",
    "uz_cyrl": "Ҳозир жавоб юбора олмадим (тармоқ хатоси). Илтимос, 1–2 дақиқадан кейин қайта ёзинг.",
    "ru": "Не могу отправить ответ сейчас (сетевая ошибка). Пожалуйста, напишите снова через 1–2 минуты.",
    "en": "Could not send a reply now (network error). Please write again in 1–2 minutes.",
    "zh": "暂时无法发送回复（网络错误）。请1–2分钟后重试。",
}

PHOTO_FALLBACK: dict[str, str] = {
    "uz_lat": "Rasmingiz qabul qilindi. Operator tez orada bog'lanadi: @sahiy_operator",
    "uz_cyrl": "Расмингиз қабул қилинди. Оператор тез орада боғланади: @sahiy_operator",
    "ru": "Ваше изображение получено. Оператор свяжется с вами в ближайшее время: @sahiy_operator",
    "en": "Your image has been received. An operator will contact you shortly: @sahiy_operator",
    "zh": "您的图片已收到。操作员将尽快联系您：@sahiy_operator",
}

NEW_CHAT_STARTED: dict[str, str] = {
    "uz_lat": "Yangi suhbat boshlandi.\n\n",
    "uz_cyrl": "Янги суҳбат бошланди.\n\n",
    "ru": "Новый диалог начат.\n\n",
    "en": "New chat started.\n\n",
    "zh": "新对话已开始。\n\n",
}

ERR_RETRY: dict[str, str] = {
    "uz_lat": "Xatolik yuz berdi. Keyinroq urinib ko'ring.",
    "uz_cyrl": "Хатолик юз берди. Кейинроқ уриниб кўринг.",
    "ru": "Произошла ошибка. Попробуйте позже.",
    "en": "An error occurred. Please try again later.",
    "zh": "发生错误。请稍后重试。",
}


def t(table: dict[str, str], lang: str) -> str:
    return table.get(lang) or table.get("uz_lat", "")
