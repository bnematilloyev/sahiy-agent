package shared

import "strings"

// Reply-language detection.
//
// Script alone is not enough here: Uzbek and Russian share the Cyrillic
// alphabet, and Uzbek customers routinely write Russian loanwords in Latin.
// Detection therefore runs a decision ladder, most reliable signal first:
//
//  1. Han characters                      -> zh
//  2. Uzbek-exclusive Cyrillic letters    -> uz-Cyrillic  (қ ғ ў ҳ)
//  3. Russian-exclusive Cyrillic letters  -> ru           (ы щ)
//  4. Cyrillic word-list scoring          -> whichever language scores higher
//  5. Latin word lists                    -> ru / uz / en
//
// When nothing is decisive it reports "not detected" so the caller can fall back
// to the customer's stored preference instead of guessing.

// uzbekOnlyCyrillic are letters that exist in Uzbek Cyrillic but not Russian.
const uzbekOnlyCyrillic = "қғўҳ"

// russianOnlyCyrillic are letters that exist in Russian but not Uzbek Cyrillic.
// ё, э and ъ are deliberately absent: both languages use them.
const russianOnlyCyrillic = "ыщ"

// russianCyrillicWords are whole words that are Russian-only or Russian-dominant.
// Loanword nouns shared with Uzbek (dostavka, zakaz, tovar) are excluded on
// purpose - they carry no signal.
var russianCyrillicWords = map[string]bool{
	// Personal and possessive pronouns
	"вы": true, "вас": true, "вам": true, "ваш": true, "ваша": true, "ваше": true, "ваши": true,
	"мы": true, "нас": true, "нам": true, "наш": true, "нашу": true, "наши": true,
	"они": true, "их": true, "им": true, "ими": true,
	"ты": true, "тебя": true, "тебе": true, "тобой": true,
	"я": true, "меня": true, "мне": true, "мной": true,
	"мой": true, "мою": true, "моя": true, "моё": true, "мои": true, "моих": true, "моему": true,
	"твой": true, "твою": true, "твоя": true, "твоё": true, "твои": true,
	"свой": true, "свою": true, "своя": true, "своё": true, "свои": true,
	// Demonstratives and interrogatives
	"это": true, "этот": true, "эта": true, "эти": true, "этого": true,
	"что": true, "чего": true, "чему": true, "чем": true,
	"где": true, "куда": true, "откуда": true,
	"когда": true, "почему": true, "зачем": true, "как": true,
	"который": true, "которая": true, "которые": true,
	// Negation, modality
	"не": true, "нет": true, "нету": true, "ни": true,
	"есть": true, "да": true,
	"можно": true, "нужно": true, "надо": true, "нельзя": true,
	// Commerce verbs in Russian grammatical forms
	"продаёте": true, "продаете": true, "продаётся": true, "продается": true,
	"продают": true, "продаю": true, "продаёт": true, "продает": true,
	"купить": true, "куплю": true, "покупаю": true, "покупать": true,
	"заказать": true, "доставки": true, "доставке": true,
	"оплатить": true, "вернуть": true,
	"стоит": true, "стоимость": true, "сколько": true, "почём": true,
	// Greetings and politeness
	"привет": true, "здравствуйте": true, "здравствуй": true, "спасибо": true,
	"пожалуйста": true, "извините": true, "скажите": true, "подскажите": true,
	// Other function words
	"или": true, "но": true, "если": true, "потому": true, "хочу": true,
	"хотел": true, "хотела": true, "хотите": true, "могу": true, "можете": true,
	"работает": true, "работаете": true, "бывает": true,
}

// russianLatinMarkers are transliterated Russian words. They are strong signals
// because an Uzbek speaker would not write them this way.
var russianLatinMarkers = []string{
	"gde", "moi", "tovary", "kogda", "pochemu",
	"spasibo", "privet", "chto", "eto",
}

// uzbekCyrillicHints are Uzbek words written in Cyrillic.
var uzbekCyrillicHints = []string{
	"борми", "борқу",
	"келмаган", "кетилмаган", "келмади",
	"товарларим", "товарим",
	"буюртма", "буюртмам", "буюртмангиз",
	"қабул", "керак", "сотасиз", "сотилади", "сотилаяпти",
	"салом", "яхши", "ёрдам", "ёки",
	"қачон", "нима", "қаерда", "қандай",
}

// uzbekLatinHints are Uzbek words in Latin script. They are also matched against
// normalized (transliterated) Cyrillic input.
var uzbekLatinHints = []string{
	"qayerda", "qachon", "qanday", "nimani",
	"buyurtma", "buyurtmalarim",
	"orderlarim", "zakazlar",
	"rahmat", "salom", "assalom",
	"tovarim", "tovarlarim",
	"kelmagan", "kemagan",
	"bormi", "kelsa", "uchun",
	"qabul", "qilgan", "kerak",
	"rasmlari", "infosi", "sotiladi",
}

// englishMarkers are matched on word boundaries so "order" does not fire inside
// the Uzbek word "orderlarim".
var englishMarkers = []string{
	"where", "when", "why", "how",
	"order", "orders", "delivery", "payment", "refund",
	"hello", "thanks", "thank you", "my order",
	"track", "shipment", "available",
}

// DetectReplyLanguage infers the language the customer is writing in. The bool
// reports whether the evidence was strong enough to act on; false means the
// caller should fall back to a stored preference rather than guess.
func DetectReplyLanguage(text string) (Language, bool) {
	raw := strings.TrimSpace(text)
	if len([]rune(raw)) < 2 {
		return LangUz, false
	}

	if hasHan(raw) {
		return LangZh, true
	}

	lower := strings.ToLower(raw)
	if strings.ContainsAny(lower, uzbekOnlyCyrillic) {
		return LangCyr, true
	}

	if hasCyrillic(lower) {
		if strings.ContainsAny(lower, russianOnlyCyrillic) {
			return LangRu, true
		}
		ru, uz := scoreCyrillic(raw)
		// Uzbek evidence wins ties: Russian has to be strictly ahead, because
		// the Russian list is much larger and would otherwise dominate.
		if ru > uz && ru > 0 {
			return LangRu, true
		}
		if uz > 0 {
			return LangCyr, true
		}
		return LangUz, false
	}

	norm := NormalizeForMatch(raw)
	if containsAnySubstring(norm, russianLatinMarkers) {
		return LangRu, true
	}
	if containsAnySubstring(norm, uzbekLatinHints) {
		return LangUz, true
	}
	if hasEnglishMarker(lower) {
		return LangEn, true
	}
	return LangUz, false
}

// languageMetaKeys are the request-metadata keys a caller may carry the
// preferred reply language in, in priority order.
//
// reply_language is this service's own name for it. locale is what the Go
// gateway integration guide asks callers to send, and was previously ignored
// outright - a caller following the documentation had its language silently
// dropped and the reply guessed from the message text instead.
var languageMetaKeys = []string{"reply_language", "locale"}

// LanguageHintFromMeta extracts the caller-supplied reply-language preference
// from request metadata, or "" when none was supplied. The value is a hint,
// not a decision: ResolveReplyLanguage still lets the customer's own wording
// override it.
func LanguageHintFromMeta(meta map[string]any) string {
	for _, key := range languageMetaKeys {
		if raw, ok := meta[key].(string); ok && strings.TrimSpace(raw) != "" {
			return raw
		}
	}
	return ""
}

// ResolveReplyLanguage picks the language to answer in.
//
// Priority: what the customer just wrote, then their stored preference, then the
// language of their recent messages, then Uzbek Latin. The current message wins
// over a stored preference on purpose - a customer who switches language expects
// the reply to switch with them.
func ResolveReplyLanguage(text, preference string, priorUserTexts []string) Language {
	if lang, ok := DetectReplyLanguage(text); ok {
		return lang
	}
	if p := strings.TrimSpace(preference); p != "" {
		if lang, ok := knownLanguage(p); ok {
			return lang
		}
	}
	// Most recent messages first.
	for i := len(priorUserTexts) - 1; i >= 0; i-- {
		if lang, ok := DetectReplyLanguage(priorUserTexts[i]); ok {
			return lang
		}
	}
	return LangUz
}

// scoreCyrillic counts Russian and Uzbek evidence in Cyrillic text.
func scoreCyrillic(text string) (russian, uzbek int) {
	lower := strings.ToLower(text)
	for _, word := range cyrillicWords(lower) {
		if russianCyrillicWords[word] {
			russian++
		}
	}

	norm := NormalizeForMatch(text)
	for _, hint := range uzbekLatinHints {
		if strings.Contains(norm, hint) {
			uzbek++
		}
	}
	for _, hint := range uzbekCyrillicHints {
		if strings.Contains(lower, hint) {
			uzbek++
		}
	}
	return russian, uzbek
}

// cyrillicWords splits text into distinct Cyrillic word tokens.
func cyrillicWords(lower string) []string {
	fields := strings.FieldsFunc(lower, func(r rune) bool {
		return !(r >= 0x0400 && r <= 0x04ff)
	})
	seen := make(map[string]bool, len(fields))
	out := make([]string, 0, len(fields))
	for _, f := range fields {
		if !seen[f] {
			seen[f] = true
			out = append(out, f)
		}
	}
	return out
}

// hasEnglishMarker matches multi-word markers as substrings and single words on
// ASCII-letter boundaries.
func hasEnglishMarker(lower string) bool {
	for _, marker := range englishMarkers {
		if strings.Contains(marker, " ") {
			if strings.Contains(lower, marker) {
				return true
			}
			continue
		}
		if containsStandaloneWord(lower, marker) {
			return true
		}
	}
	return false
}

func containsStandaloneWord(text, word string) bool {
	for i := 0; ; {
		idx := strings.Index(text[i:], word)
		if idx < 0 {
			return false
		}
		start := i + idx
		end := start + len(word)
		if !isASCIILetterAt(text, start-1) && !isASCIILetterAt(text, end) {
			return true
		}
		i = start + 1
		if i >= len(text) {
			return false
		}
	}
}

func isASCIILetterAt(text string, i int) bool {
	if i < 0 || i >= len(text) {
		return false
	}
	c := text[i]
	return c >= 'a' && c <= 'z'
}

func containsAnySubstring(text string, needles []string) bool {
	for _, n := range needles {
		if strings.Contains(text, n) {
			return true
		}
	}
	return false
}

func hasHan(text string) bool {
	for _, r := range text {
		if r >= 0x4e00 && r <= 0x9fff {
			return true
		}
	}
	return false
}

// knownLanguage parses a stored preference, rejecting unknown codes so a typo
// does not silently become Uzbek.
func knownLanguage(raw string) (Language, bool) {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "uz", "uz_lat", "uz-latn", "lat", "latin":
		return LangUz, true
	case "cyr", "uz_cyrl", "uz-cyrl", "cyrillic":
		return LangCyr, true
	case "ru", "rus", "russian":
		return LangRu, true
	case "en", "eng", "english":
		return LangEn, true
	case "zh", "cn", "chinese", "zh-cn":
		return LangZh, true
	default:
		return LangUz, false
	}
}
