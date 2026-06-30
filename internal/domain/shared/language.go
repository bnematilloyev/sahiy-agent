package shared

import (
	"strings"
	"unicode"
)

// Language is a value object for the reply language. Supported codes mirror the
// FAQ localization columns: uz (Latin), cyr (Uzbek Cyrillic), ru, en, zh.
type Language struct {
	code string
}

// Supported languages.
var (
	LangUz  = Language{code: "uz"}
	LangCyr = Language{code: "cyr"}
	LangRu  = Language{code: "ru"}
	LangEn  = Language{code: "en"}
	LangZh  = Language{code: "zh"}
)

// NewLanguage normalizes a code (or a market/python hint like "uz_lat",
// "uz_cyrl") into a Language, defaulting to Uzbek Latin when unrecognized.
func NewLanguage(raw string) Language {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "uz", "uz_lat", "uz-latn", "lat", "latin":
		return LangUz
	case "cyr", "uz_cyrl", "uz-cyrl", "cyrillic":
		return LangCyr
	case "ru", "rus", "russian":
		return LangRu
	case "en", "eng", "english":
		return LangEn
	case "zh", "cn", "chinese", "zh-cn":
		return LangZh
	default:
		return LangUz
	}
}

// Code returns the canonical short code (also the FAQ locale key).
func (l Language) Code() string { return l.code }

// EnglishName returns a human-readable name used to instruct the LLM which
// language to answer in.
func (l Language) EnglishName() string {
	switch l.code {
	case LangCyr.code:
		return "Uzbek (Cyrillic script)"
	case LangRu.code:
		return "Russian"
	case LangEn.code:
		return "English"
	case LangZh.code:
		return "Chinese"
	default:
		return "Uzbek (Latin script)"
	}
}

// DetectLanguage infers the reply language from message text using script
// heuristics. It is pure and side-effect free.
func DetectLanguage(text string) Language {
	var hasCJK, hasCyrillic, hasUzbekCyrillic bool
	for _, r := range text {
		switch {
		case unicode.Is(unicode.Han, r):
			hasCJK = true
		case unicode.Is(unicode.Cyrillic, r):
			hasCyrillic = true
			// Uzbek-specific Cyrillic letters distinguish uz-cyrl from ru.
			if strings.ContainsRune("ўқғҳЎҚҒҲ", r) {
				hasUzbekCyrillic = true
			}
		}
	}
	switch {
	case hasCJK:
		return LangZh
	case hasUzbekCyrillic:
		return LangCyr
	case hasCyrillic:
		return LangRu
	default:
		return LangUz
	}
}
