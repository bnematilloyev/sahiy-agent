package routing_test

import (
	"testing"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/routing"
)

// Keyword rules are written in Latin only; Cyrillic input must hit the same
// rule after normalization, so no rule needs a duplicate Cyrillic entry.
func TestOperatorRequestAcrossScripts(t *testing.T) {
	for _, text := range []string{
		"operator bilan bog'lanish",
		"оператор билан боғланинг",
		"позовите оператора",
		"хочу поговорить с человеком",
		"menejer chaqiring",
	} {
		if !routing.IsOperatorRequest(text) {
			t.Errorf("IsOperatorRequest(%q) = false, want true", text)
		}
	}
	if routing.IsOperatorRequest("yetkazib berish qancha vaqt") {
		t.Error("a delivery question must not read as an operator request")
	}
}

func TestChitchatAcrossScripts(t *testing.T) {
	for _, text := range []string{"salom", "привет", "спасибо", "раҳмат"} {
		if !routing.IsChitchat(text) {
			t.Errorf("IsChitchat(%q) = false, want true", text)
		}
	}
	if routing.IsChitchat("salom, buyurtmam qachon keladi va qancha turadi") {
		t.Error("a long question must not be swallowed as chitchat")
	}
}

// Typographic apostrophes must not defeat a rule: bo'lsa / boʻlsa / bo‘lsa are
// the same word to a customer.
func TestApostropheVariantsMatch(t *testing.T) {
	for _, text := range []string{"zo'r", "zoʻr", "zo‘r"} {
		if !routing.IsChitchat(text) {
			t.Errorf("IsChitchat(%q) = false, want true", text)
		}
	}
}

func TestIsProfanity(t *testing.T) {
	if !routing.IsProfanity("sen ahmoq ekansan") {
		t.Error("expected profanity to be detected")
	}
	if !routing.IsProfanity("итдан тарқаган") {
		t.Error("expected Cyrillic profanity phrase to be detected")
	}
	if routing.IsProfanity("buyurtmam qachon keladi") {
		t.Error("an ordinary question must not be flagged")
	}
}

// Word-boundary matching: a listed word must not fire from inside a longer,
// innocent word. This is the false positive the Python substring check had.
func TestProfanityDoesNotMatchInsideWords(t *testing.T) {
	if routing.IsProfanity("dalada ishlayman") {
		t.Error(`"dalada" must not trigger the "dala" rule`)
	}
	if routing.IsProfanity("eshakdanmi") {
		t.Error(`"eshakdanmi" must not trigger the "eshak" rule`)
	}
}

func TestIsCompanyQuestion(t *testing.T) {
	for _, text := range []string{
		"sahiy nima?",
		"Sahiy qanday ishlaydi",
		"Sahiy haqida ma'lumot bering",
		"саҳий нима",
	} {
		if !routing.IsCompanyQuestion(text) {
			t.Errorf("IsCompanyQuestion(%q) = false, want true", text)
		}
	}
}

// Mentioning Sahiy is not enough - the message must actually ask about the
// company, not about the customer's own order.
func TestCompanyQuestionNeedsBothSignals(t *testing.T) {
	if routing.IsCompanyQuestion("sahiy orqali buyurtma berdim, qachon keladi") {
		t.Error("an order question that mentions Sahiy must not get the company blurb")
	}
	if routing.IsCompanyQuestion("bu nima degani") {
		t.Error("a question without Sahiy must not get the company blurb")
	}
}
