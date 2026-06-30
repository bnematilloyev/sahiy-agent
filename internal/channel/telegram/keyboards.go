package telegram

import (
	"github.com/go-telegram/bot/models"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

func languageInlineKeyboard() *models.InlineKeyboardMarkup {
	return &models.InlineKeyboardMarkup{
		InlineKeyboard: [][]models.InlineKeyboardButton{
			{
				{Text: "🇺🇿 O'zbek", CallbackData: "lang_uz"},
				{Text: "🇷🇺 Русский", CallbackData: "lang_ru"},
			},
			{
				{Text: "🇬🇧 English", CallbackData: "lang_en"},
				{Text: "🇨🇳 中文", CallbackData: "lang_zh"},
			},
		},
	}
}

func ratingInlineKeyboard() *models.InlineKeyboardMarkup {
	return &models.InlineKeyboardMarkup{
		InlineKeyboard: [][]models.InlineKeyboardButton{
			{
				{Text: "⭐", CallbackData: "rate_1"},
				{Text: "⭐⭐", CallbackData: "rate_2"},
				{Text: "⭐⭐⭐", CallbackData: "rate_3"},
				{Text: "⭐⭐⭐⭐", CallbackData: "rate_4"},
				{Text: "⭐⭐⭐⭐⭐", CallbackData: "rate_5"},
			},
		},
	}
}

func phoneRequestKeyboard(lang shared.Language) models.ReplyMarkup {
	return &models.ReplyKeyboardMarkup{
		Keyboard: [][]models.KeyboardButton{
			{{Text: phoneButtonLabel(lang), RequestContact: true}},
		},
		ResizeKeyboard:  true,
		OneTimeKeyboard: true,
	}
}

func mainMenuKeyboard(lang shared.Language) models.ReplyMarkup {
	labels := labelsFor(lang)
	return &models.ReplyKeyboardMarkup{
		Keyboard: [][]models.KeyboardButton{
			{{Text: labels.callback}, {Text: labels.newChat}},
			{{Text: labels.language}, {Text: labels.help}},
			{{Text: labels.productSearch}},
		},
		ResizeKeyboard: true,
		IsPersistent:   true,
	}
}

type menuLabelSet struct {
	callback, newChat, language, help, productSearch string
}

func labelsFor(lang shared.Language) menuLabelSet {
	switch lang.Code() {
	case shared.LangRu.Code():
		return menuLabelSet{
			callback: "📞 Обратный звонок", newChat: "🔄 Новый чат",
			language: "🌐 Сменить язык", help: "❓ Помощь", productSearch: "🔍 Поиск товаров",
		}
	case shared.LangEn.Code():
		return menuLabelSet{
			callback: "📞 Request a call", newChat: "🔄 New chat",
			language: "🌐 Change language", help: "❓ Help", productSearch: "🔍 Search products",
		}
	case shared.LangCyr.Code():
		return menuLabelSet{
			callback: "📞 Қайта қўнғироқ", newChat: "🔄 Янги суҳбат",
			language: "🌐 Тилни ўзгартириш", help: "❓ Ёрдам", productSearch: "🔍 Маҳsulot qidirish",
		}
	case shared.LangZh.Code():
		return menuLabelSet{
			callback: "📞 回电请求", newChat: "🔄 新对话",
			language: "🌐 更改语言", help: "❓ 帮助", productSearch: "🔍 搜索商品",
		}
	default:
		return menuLabelSet{
			callback: "📞 Qayta qo'ng'iroq", newChat: "🔄 Yangi suhbat",
			language: "🌐 Tilni o'zgartirish", help: "❓ Yordam", productSearch: "🔍 Mahsulot qidirish",
		}
	}
}

func phoneButtonLabel(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "📱 Отправить номер телефона"
	case shared.LangEn.Code():
		return "📱 Send phone number"
	case shared.LangCyr.Code():
		return "📱 Телефон рақамни юбориш"
	case shared.LangZh.Code():
		return "📱 发送电话号码"
	default:
		return "📱 Telefon raqamni yuborish"
	}
}

func matchMenuAction(text string, lang shared.Language) (string, bool) {
	labels := labelsFor(lang)
	switch text {
	case labels.newChat:
		return "new_chat", true
	case labels.language:
		return "language", true
	case labels.help:
		return "help", true
	case labels.callback:
		return "callback", true
	case labels.productSearch:
		return "product_search", true
	default:
		return "", false
	}
}
