package telegram

import "github.com/sahiy-backend/sahiy-agent/internal/domain/shared"

// i18n string keys for Telegram-only copy.
const (
	LanguagePickerPrompt = "language_picker"
	Welcome              = "welcome"
	PhonePrompt          = "phone_prompt"
	PhoneSaved           = "phone_saved"
	PhoneWrongContact    = "phone_wrong"
	NewChatStarted       = "new_chat"
	FallbackError        = "fallback_error"
	ErrRetry             = "err_retry"
	MenuHelp             = "menu_help"
	MenuCallbackText     = "menu_callback_text"
	ProductSearchPrompt  = "product_search_prompt"
	ProductSearchTooShort = "product_search_short"
	RatingPrompt         = "rating_prompt"
	RatingThanks         = "rating_thanks"
)

var stringsTable = map[string]map[string]string{
	LanguagePickerPrompt: {
		"uz":  "🌐 Muloqot tilini tanlang:\nQuyidagi tugmalardan birini bosing 👇",
		"cyr": "🌐 Мулоқот тилini танlang:\nQuyidagi tugmalardan birini bosing 👇",
		"ru":  "🌐 Выберите язык общения:\nНажмите одну из кнопок ниже 👇",
		"en":  "🌐 Choose your language:\nTap one of the buttons below 👇",
		"zh":  "🌐 请选择对话语言：\n点击下方按钮 👇",
	},
	Welcome: {
		"uz":  "Assalomu alaykum! Men Sahiy yordamchi botiman.\n\nSavolingizni yozing yoki menyu tugmalaridan foydalaning.\nYangi suhbat: /new",
		"cyr": "Ассалому алайкум! Мен Sahiy ёрдамчи ботiman.\n\nСаволингизни ёzing ёки меню tugmalaridan foydalaning.\nЯнги суҳбат: /new",
		"ru":  "Здравствуйте! Я помощник Sahiy.\n\nНапишите ваш вопрос или используйте меню.\nНовый чат: /new",
		"en":  "Hello! I'm the Sahiy assistant bot.\n\nWrite your question or use the menu.\nNew chat: /new",
		"zh":  "您好！我是Sahiy助理机器人。\n\n请提问或使用菜单。\n新对话：/new",
	},
	PhonePrompt: {
		"uz":  "Davom etish uchun telefon raqamingizni «Telefon raqamni yuborish» tugmasi orqali yuboring.",
		"cyr": "Давom etish uchun telefon raqamingizni yuboring.",
		"ru":  "Для продолжения отправьте номер телефона кнопкой ниже.",
		"en":  "To continue, send your phone number using the button below.",
		"zh":  "请使用下方按钮发送您的电话号码以继续。",
	},
	PhoneSaved: {
		"uz":  "Rahmat! Telefon raqamingiz saqlandi. Endi savolingizni yozing.",
		"cyr": "Раҳmat! Telefon raqamingiz saqlandi.",
		"ru":  "Спасибо! Номер сохранён. Теперь напишите ваш вопрос.",
		"en":  "Thank you! Phone saved. Now write your question.",
		"zh":  "谢谢！电话号码已保存。请提出您的问题。",
	},
	PhoneWrongContact: {
		"uz":  "Telefon raqam noto'g'ri. O'zingizning raqamingizni yuboring.",
		"ru":  "Неверный номер. Отправьте свой номер телефона.",
		"en":  "Invalid phone. Please send your own number.",
		"zh":  "电话号码无效。请发送您自己的号码。",
	},
	NewChatStarted: {
		"uz":  "Yangi suhbat boshlandi.",
		"ru":  "Начат новый чат.",
		"en":  "New chat started.",
		"zh":  "已开始新对话。",
	},
	FallbackError: {
		"uz":  "Kechirasiz, vaqtincha javob bera olmadim. Qayta urinib ko'ring.",
		"ru":  "Извините, не удалось ответить. Попробуйте ещё раз.",
		"en":  "Sorry, I couldn't respond. Please try again.",
		"zh":  "抱歉，暂时无法回复。请重试。",
	},
	ErrRetry: {
		"uz":  "Xatolik yuz berdi. /new buyrug'i bilan qayta urinib ko'ring.",
		"en":  "Something went wrong. Try /new to start over.",
	},
	MenuHelp: {
		"uz":  "Men buyurtma, topshirish punktlari, mahsulot qidiruv va FAQ bo'yicha yordam bera olaman.\nYangi suhbat: /new",
		"ru":  "Я помогаю с заказами, пунктами выдачи, поиском товаров и FAQ.\nНовый чат: /new",
		"en":  "I can help with orders, pickup points, product search, and FAQ.\nNew chat: /new",
	},
	MenuCallbackText: {
		"uz":  "Operator bilan bog'lanishni xohlayman",
		"ru":  "Хочу связаться с оператором",
		"en":  "I want to speak to an operator",
	},
	ProductSearchPrompt: {
		"uz":  "Mahsulot nomini yozing (masalan: kiyim, telefon)...",
		"ru":  "Введите название товара (например: одежда, телефон)...",
		"en":  "Enter a product name (e.g. clothing, phone)...",
	},
	ProductSearchTooShort: {
		"uz":  "Kamida 2 ta harf yozing.",
		"ru":  "Введите минимум 2 символа.",
		"en":  "Enter at least 2 characters.",
	},
	RatingPrompt: {
		"uz":  "Xizmatimizni baholang:",
		"ru":  "Оцените наш сервис:",
		"en":  "Please rate our service:",
	},
	RatingThanks: {
		"uz":  "Rahmat! Baho: %d ⭐",
		"ru":  "Спасибо! Оценка: %d ⭐",
		"en":  "Thank you! Rating: %d ⭐",
	},
}

// T returns localized Telegram copy.
func T(key string, lang shared.Language) string {
	table, ok := stringsTable[key]
	if !ok {
		return key
	}
	if s, ok := table[lang.Code()]; ok && s != "" {
		return s
	}
	if s, ok := table["uz"]; ok {
		return s
	}
	return key
}
