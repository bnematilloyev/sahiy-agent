package shared

import "strings"

// cyrillicToLatin maps Uzbek and Russian Cyrillic letters onto the Latin forms
// used by the keyword lists, so a rule written once matches both scripts.
// It is a matching aid, not a transliteration service: the output is meant for
// comparison, never for display to a customer.
var cyrillicToLatin = map[rune]string{
	'щ': "sh", 'ш': "sh", 'ч': "ch", 'ц': "ts", 'ё': "yo", 'ю': "yu", 'я': "ya",
	'ғ': "g'", 'ў': "o'", 'қ': "q", 'ҳ': "h", 'ж': "j", 'ъ': "'", 'ь': "'",
	'э': "e", 'ы': "y",
	'а': "a", 'б': "b", 'в': "v", 'г': "g", 'д': "d", 'е': "e", 'з': "z",
	'и': "i", 'й': "y", 'к': "k", 'л': "l", 'м': "m", 'н': "n", 'о': "o",
	'п': "p", 'р': "r", 'с': "s", 'т': "t", 'у': "u", 'ф': "f", 'х': "x",
}

// apostrophes are the typographic variants Uzbek text uses for oʻ/gʻ. They are
// folded to a plain ASCII quote so "bo'lsa", "boʻlsa" and "bo‘lsa" all match.
var apostrophes = strings.NewReplacer("ʻ", "'", "ʼ", "'", "‘", "'", "’", "'", "`", "'")

// NormalizeForMatch lowercases text, folds apostrophe variants and transliterates
// Cyrillic to Latin. Every keyword rule compares normalized strings, so a rule
// only has to be written in Uzbek Latin.
func NormalizeForMatch(text string) string {
	t := apostrophes.Replace(strings.ToLower(strings.TrimSpace(text)))
	if !hasCyrillic(t) {
		return t
	}
	var b strings.Builder
	b.Grow(len(t))
	for _, r := range t {
		if latin, ok := cyrillicToLatin[r]; ok {
			b.WriteString(latin)
			continue
		}
		b.WriteRune(r)
	}
	return b.String()
}

func hasCyrillic(text string) bool {
	for _, r := range text {
		if r >= 0x0400 && r <= 0x04ff {
			return true
		}
	}
	return false
}
