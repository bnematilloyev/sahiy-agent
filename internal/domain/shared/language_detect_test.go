package shared

import "testing"

func TestDetectReplyLanguageByScript(t *testing.T) {
	cases := map[string]Language{
		"配送需要多长时间":                LangZh,
		"Буюртмам қачон келади?":  LangCyr, // қ is Uzbek-only
		"Что с моим заказом?":     LangRu,
		"Buyurtmam qachon keladi": LangUz,
		"where is my order":       LangEn,
	}
	for text, want := range cases {
		got, ok := DetectReplyLanguage(text)
		if !ok {
			t.Errorf("DetectReplyLanguage(%q) was inconclusive, want %s", text, want.Code())
			continue
		}
		if got.Code() != want.Code() {
			t.Errorf("DetectReplyLanguage(%q) = %s, want %s", text, got.Code(), want.Code())
		}
	}
}

// The hard case the script heuristic alone gets wrong: Uzbek and Russian share
// the Cyrillic alphabet, so word evidence has to decide.
func TestDetectDistinguishesUzbekAndRussianCyrillic(t *testing.T) {
	uzbek := []string{
		"буюртмам келмаган",
		"товарларим борми",
		"салом ёрдам керак",
	}
	for _, text := range uzbek {
		got, ok := DetectReplyLanguage(text)
		if !ok || got.Code() != LangCyr.Code() {
			t.Errorf("DetectReplyLanguage(%q) = %s (ok=%v), want cyr", text, got.Code(), ok)
		}
	}

	russian := []string{
		"когда придет мой заказ",
		"сколько стоит доставка",
		"здравствуйте подскажите пожалуйста",
	}
	for _, text := range russian {
		got, ok := DetectReplyLanguage(text)
		if !ok || got.Code() != LangRu.Code() {
			t.Errorf("DetectReplyLanguage(%q) = %s (ok=%v), want ru", text, got.Code(), ok)
		}
	}
}

// Latin-script Russian is common from Uzbek keyboards and must not be read as
// Uzbek just because it uses the Latin alphabet.
func TestDetectLatinRussian(t *testing.T) {
	for _, text := range []string{"gde moi zakaz", "spasibo bolshoe", "privet kogda dostavka"} {
		got, ok := DetectReplyLanguage(text)
		if !ok || got.Code() != LangRu.Code() {
			t.Errorf("DetectReplyLanguage(%q) = %s (ok=%v), want ru", text, got.Code(), ok)
		}
	}
}

// "order" must not fire inside the Uzbek word "orderlarim".
func TestEnglishMarkersRespectWordBoundaries(t *testing.T) {
	got, ok := DetectReplyLanguage("orderlarim qayerda")
	if !ok || got.Code() != LangUz.Code() {
		t.Errorf("DetectReplyLanguage = %s (ok=%v), want uz", got.Code(), ok)
	}
}

// Too little evidence must be reported as inconclusive rather than guessed, so
// the caller can use the customer's stored preference instead.
func TestDetectReportsInconclusive(t *testing.T) {
	for _, text := range []string{"", "?", "ok", "12345", "+998901112233"} {
		if _, ok := DetectReplyLanguage(text); ok {
			t.Errorf("DetectReplyLanguage(%q) claimed a language, want inconclusive", text)
		}
	}
}

// A customer who switches language mid-conversation expects the reply to switch
// with them, so the current message outranks the stored preference.
func TestResolvePrefersCurrentMessageOverPreference(t *testing.T) {
	got := ResolveReplyLanguage("Что с моим заказом?", "uz_lat", nil)
	if got.Code() != LangRu.Code() {
		t.Errorf("ResolveReplyLanguage = %s, want ru", got.Code())
	}
}

func TestResolveFallsBackToPreference(t *testing.T) {
	got := ResolveReplyLanguage("+998901112233", "ru", nil)
	if got.Code() != LangRu.Code() {
		t.Errorf("ResolveReplyLanguage = %s, want the stored preference ru", got.Code())
	}
}

// With no preference, the language of earlier messages carries the conversation.
func TestResolveFallsBackToHistory(t *testing.T) {
	history := []string{"salom", "когда придет мой заказ"}
	got := ResolveReplyLanguage("12345", "", history)
	if got.Code() != LangRu.Code() {
		t.Errorf("ResolveReplyLanguage = %s, want ru from the most recent decisive message", got.Code())
	}
}

func TestResolveDefaultsToUzbekLatin(t *testing.T) {
	if got := ResolveReplyLanguage("?", "", nil); got.Code() != LangUz.Code() {
		t.Errorf("ResolveReplyLanguage = %s, want uz", got.Code())
	}
}

// An unrecognized stored preference must not silently pass through.
func TestResolveIgnoresUnknownPreference(t *testing.T) {
	if got := ResolveReplyLanguage("12345", "klingon", nil); got.Code() != LangUz.Code() {
		t.Errorf("ResolveReplyLanguage = %s, want the uz default", got.Code())
	}
}

func TestLanguageHintFromMeta(t *testing.T) {
	cases := []struct {
		name string
		meta map[string]any
		want string
	}{
		{"canonical key", map[string]any{"reply_language": "ru"}, "ru"},
		// The integration guide tells callers to send "locale"; ignoring it made
		// a caller that followed the documentation have its language dropped.
		{"documented locale key", map[string]any{"locale": "en"}, "en"},
		{"reply_language wins", map[string]any{"locale": "en", "reply_language": "ru"}, "ru"},
		{"blank is not a hint", map[string]any{"reply_language": "  ", "locale": "ru"}, "ru"},
		{"wrong type ignored", map[string]any{"reply_language": 7, "locale": "ru"}, "ru"},
		{"nothing supplied", map[string]any{"channel": "web"}, ""},
		{"nil meta", nil, ""},
	}
	for _, c := range cases {
		if got := LanguageHintFromMeta(c.meta); got != c.want {
			t.Errorf("%s: LanguageHintFromMeta = %q, want %q", c.name, got, c.want)
		}
	}
}

// The hint must actually reach the resolved language when the text itself is
// inconclusive - that is the whole point of accepting it.
func TestLocaleHintDrivesReplyLanguage(t *testing.T) {
	if got := ResolveReplyLanguage("123456", LanguageHintFromMeta(map[string]any{"locale": "ru"}), nil); got.Code() != "ru" {
		t.Errorf("locale hint did not reach the reply language: got %q", got.Code())
	}
}
