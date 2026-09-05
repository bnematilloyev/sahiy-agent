package chat

import (
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/routing"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// StaticAnswers implements faq.StaticAnswerer. The FAQ service consults it only
// when retrieval found no knowledge-base entry, so a real entry always wins over
// the hardcoded copy below.
type StaticAnswers struct{}

// StaticAnswer returns a fixed reply for questions we know the knowledge base
// may not cover.
func (StaticAnswers) StaticAnswer(text string, lang shared.Language) (string, bool) {
	if routing.IsCompanyQuestion(text) {
		return companyMessage(lang), true
	}
	return "", false
}

// This file holds the assistant's deterministic, customer-facing copy: the
// replies produced without asking a model. Keeping it in one place makes the
// full set of hardcoded strings reviewable by the support team.
//
// NOTE: companyMessage states delivery times and catalog size. Business facts
// in source code go stale silently and need a deploy to change - once the FAQ
// knowledge base covers "what is Sahiy", this should be deleted in favour of it.

// withOperatorNotice appends a handoff notice to a low-confidence answer, so the
// customer is told the reply is uncertain instead of reading it as final.
func withOperatorNotice(text string, lang shared.Language) string {
	notice := operatorNotice(lang)
	if strings.TrimSpace(text) == "" {
		return notice
	}
	return text + "\n\n" + notice
}

func operatorNotice(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Чтобы вы получили точный ответ, подключаю оператора."
	case shared.LangEn.Code():
		return "To make sure you get an accurate answer, I'm connecting an operator."
	case shared.LangCyr.Code():
		return "Аниқ жавоб олишингиз учун операторни улаяпман."
	case shared.LangZh.Code():
		return "为确保答复准确，正在为您接通人工客服。"
	default:
		return "Aniq javob olishingiz uchun operatorni ulayapman."
	}
}

// greetingMessage is the deterministic reply to small talk when no model is
// available. Greetings do not need an operator.
func greetingMessage(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Здравствуйте! Чем могу помочь?"
	case shared.LangEn.Code():
		return "Hello! How can I help you?"
	case shared.LangCyr.Code():
		return "Ассалому алайкум! Сизга қандай ёрдам бера оламан?"
	case shared.LangZh.Code():
		return "您好！有什么可以帮您？"
	default:
		return "Assalomu alaykum! Sizga qanday yordam bera olaman?"
	}
}

func operatorMessage(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Соединяю вас с оператором. Пожалуйста, подождите."
	case shared.LangEn.Code():
		return "Connecting you to an operator. Please wait a moment."
	case shared.LangCyr.Code():
		return "Сизни оператор билан боғлаяпман. Илтимос, бироз кутиб туринг."
	case shared.LangZh.Code():
		return "正在为您接通人工客服，请稍候。"
	default:
		return "Sizni operator bilan bog'layapman. Iltimos, biroz kuting."
	}
}

// civilityMessage answers an insult with a request for mutual respect instead of
// sending it to a model. Ported from the Python service.
func civilityMessage(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Пожалуйста, давайте общаться уважительно. Если у вас есть вопросы по сервису Sahiy, я готов помочь."
	case shared.LangEn.Code():
		return "Please let's keep our conversation respectful. If you have questions about the Sahiy service, I'm happy to help."
	case shared.LangCyr.Code():
		return "Илтимос, мулоқотда ўзаро ҳурматни сақлайлик. Sahiy хизматига оид саволларингиз бўлса, ёрдам беришга тайёрман."
	case shared.LangZh.Code():
		return "请让我们保持互相尊重的交流。如果您有关于 Sahiy 服务的问题，我很乐意为您解答。"
	default:
		return "Iltimos, muloqotda o'zaro hurmatni saqlaylik. Sahiy xizmatiga oid savollaringiz bo'lsa, yordam berishga tayyorman."
	}
}

// companyMessage is the static "what is Sahiy" answer. Ported from the Python
// service, which used it whenever the knowledge base missed the question.
func companyMessage(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Sahiy — платформа для заказа товаров из Китая.\n" +
			"\n" +
			"- Срок доставки: 12–15 дней (регионы: 20 дней)\n" +
			"- Более миллиона наименований товаров\n" +
			"- Одежда, электроника, товары для дома и другое\n" +
			"\n" +
			"Пишите, если есть вопросы — отправьте трек-номер или свой вопрос."
	case shared.LangEn.Code():
		return "Sahiy is a platform for ordering goods from China.\n" +
			"\n" +
			"- Delivery time: 12-15 days (regions: 20 days)\n" +
			"- Over a million product types\n" +
			"- Clothing, electronics, household goods and more\n" +
			"\n" +
			"Feel free to write — send a tracking number or your question."
	case shared.LangCyr.Code():
		return "Sahiy — Хитойдан товар буюртма қилиш платформаси.\n" +
			"\n" +
			"- Етказиш муддати: 12–15 кун (вилоят: 20 кун)\n" +
			"- Миллиондан ортиқ маҳсулот тури\n" +
			"- Кийим, электроника, уй-рўзғор ва бошқалар\n" +
			"\n" +
			"Савол бўлса ёзаверинг — track рақам ёки саволингизни юборинг."
	case shared.LangZh.Code():
		return "Sahiy 是从中国订购商品的平台。\n" +
			"\n" +
			"- 配送时间：12-15 天（外地：20 天）\n" +
			"- 超过一百万种商品\n" +
			"- 服装、电子产品、家居用品等\n" +
			"\n" +
			"有问题请随时联系我们 — 发送快递单号或您的问题。"
	default:
		return "Sahiy — Xitoydan tovar buyurtma qilish platformasi.\n" +
			"\n" +
			"- Yetkazish muddati: 12–15 kun (viloyat: 20 kun)\n" +
			"- Milliondan ortiq mahsulot turi\n" +
			"- Kiyim, elektronika, uy-ro'zg'or va boshqalar\n" +
			"\n" +
			"Savol bo'lsa yozavering — track raqam yoki savolingizni yuboring."
	}
}
