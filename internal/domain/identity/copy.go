package identity

import "github.com/sahiy-backend/sahiy-agent/internal/domain/shared"

func IdentityRequiredText(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "📱 Для продолжения необходим аккаунт Sahiy.\n\nОтправьте одно из следующего:\n- ID аккаунта — например: 111111 или id 111111\n- Телефон — 998901234567 или кнопка «Отправить номер телефона»\n\nПосле подтверждения отвечу на ваш вопрос."
	case shared.LangEn.Code():
		return "📱 A Sahiy account is required to continue.\n\nPlease send one of the following:\n- Account ID — e.g.: 111111 or id 111111\n- Phone — 998901234567 or tap «Send phone number»\n\nI'll answer your question after verification."
	case shared.LangCyr.Code():
		return "📱 Давом этиш учун Sahiy ҳисобингиз керак.\n\nҚуйидагилардан бирини юборинг:\n- Ҳисоб ID — масалан: 111111 ёки id 111111\n- Телефон — 998901234567 ёки «Телефон рақамни юбориш» тугмаси\n\nТасдиқлангач саволингизга жавоб бераман."
	case shared.LangZh.Code():
		return "📱 继续操作需要Sahiy账户。\n\n请发送以下其中一项：\n- 账户ID — 例如：111111 或 id 111111\n- 电话 — 998901234567 或点击«发送电话号码»\n\n验证后我将回答您的问题。"
	default:
		return "📱 Davom etish uchun Sahiy hisobingiz kerak.\n\nQuyidagilardan birini yuboring:\n- Hisob ID — masalan: 111111 yoki id 111111\n- Telefon — 998901234567 yoki «Telefon raqamni yuborish» tugmasi\n\nTasdiqlangach savolingizni yozing."
	}
}

func InvalidPhoneFormatText(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "❌ Неверный формат номера телефона.\n\nПример: 998901234567 или +998 90 123 45 67\nОтправьте снова."
	case shared.LangEn.Code():
		return "❌ Invalid phone format.\n\nExample: 998901234567 or +998 90 123 45 67\nPlease send again."
	default:
		return "❌ Telefon formati noto'g'ri.\n\nTo'g'ri misol: 998901234567 yoki +998 90 123 45 67\nQayta yuboring."
	}
}

func PhoneNotRegisteredText(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "❌ Этот телефон не найден в системе Sahiy.\n\nОтправьте номер, зарегистрированный в приложении, или используйте кнопку «Отправить номер телефона»."
	case shared.LangEn.Code():
		return "❌ This phone number was not found in Sahiy system.\n\nSend the number registered in the app, or use the «Send phone number» button."
	default:
		return "❌ Bu telefon Sahiy tizimida topilmadi.\n\nIlovada ro'yxatdan o'tgan raqamni yuboring yoki «Telefon raqamni yuborish» tugmasidan foydalaning."
	}
}

func PhoneVerifiedText(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "✅ Телефон подтверждён. Теперь напишите ваш вопрос."
	case shared.LangEn.Code():
		return "✅ Phone confirmed. Now write your question."
	default:
		return "✅ Telefon tasdiqlandi. Endi buyurtma yoki boshqa savolingizni yozing."
	}
}

func SahiyUserIDVerifiedText(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "✅ ID аккаунта принят. Теперь напишите ваш вопрос."
	case shared.LangEn.Code():
		return "✅ Account ID accepted. Now write your question."
	default:
		return "✅ Hisob ID qabul qilindi. Endi savolingizni yozing."
	}
}

func SahiyUserIDInvalidText(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "❌ Неверный ID аккаунта.\n\nНапример: 111111 или id 191052 — напишите номер вашего аккаунта в приложении."
	case shared.LangEn.Code():
		return "❌ Invalid account ID.\n\nExample: 111111 or id 191052 — write your app account number."
	default:
		return "❌ Hisob ID noto'g'ri.\n\nMasalan: 111111 yoki id 191052 — ilovadagi hisob raqamingizni yozing."
	}
}

func SahiyUserIDNotFoundText(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "❌ Клиент с таким ID аккаунта не найден.\n\nОтправьте номер телефона или проверьте другой ID."
	case shared.LangEn.Code():
		return "❌ No customer found with this account ID.\n\nSend your phone number or check another ID."
	default:
		return "❌ Bu hisob ID bo'yicha mijoz topilmadi.\n\nTelefon raqamini yuboring yoki boshqa ID ni tekshirib ko'ring."
	}
}

func APIUnavailableText(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Не удалось проверить аккаунт (API временно недоступен). Попробуйте снова через несколько минут."
	case shared.LangEn.Code():
		return "Could not verify account (API temporarily unavailable). Please try again in a few minutes."
	default:
		return "Hozir mijozni tekshirib bo'lmadi (API vaqtincha ishlamayapti). Bir necha daqiqadan keyin qayta urinib ko'ring."
	}
}
