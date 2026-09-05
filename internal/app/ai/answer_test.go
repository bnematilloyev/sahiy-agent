package ai

import "testing"

func TestParseAnswerHonoursContract(t *testing.T) {
	parsed, ok := ParseAnswer(`{"answer":"Yetkazib berish 7-10 kun.","confidence":0.92}`)
	if !ok {
		t.Fatal("expected the contract to be recognised")
	}
	if parsed.Text != "Yetkazib berish 7-10 kun." {
		t.Errorf("Text = %q", parsed.Text)
	}
	if parsed.Confidence != 0.92 {
		t.Errorf("Confidence = %v, want 0.92", parsed.Confidence)
	}
}

func TestParseAnswerToleratesCodeFences(t *testing.T) {
	raw := "Here you go:\n```json\n{\"answer\":\"Salom\",\"confidence\":0.7}\n```"
	parsed, ok := ParseAnswer(raw)
	if !ok {
		t.Fatal("expected fenced JSON to parse")
	}
	if parsed.Text != "Salom" || parsed.Confidence != 0.7 {
		t.Errorf("parsed = %+v", parsed)
	}
}

// A model that answers in prose must not be trusted: the reply is still usable
// but has to score low enough to trigger escalation.
func TestParseAnswerProseFallsBackToLowConfidence(t *testing.T) {
	parsed, ok := ParseAnswer("Buyurtmangiz yo'lda, 3 kunda yetadi.")
	if ok {
		t.Fatal("prose must not be reported as contract-compliant")
	}
	if parsed.Text != "Buyurtmangiz yo'lda, 3 kunda yetadi." {
		t.Errorf("Text = %q, want the raw prose preserved", parsed.Text)
	}
	if parsed.Confidence >= 0.45 {
		t.Errorf("Confidence = %v, must stay below the default escalation threshold", parsed.Confidence)
	}
}

func TestParseAnswerRejectsPartialContract(t *testing.T) {
	// "confidence" missing entirely: the model did not self-assess, so its
	// wording must not inherit a high score.
	parsed, ok := ParseAnswer(`{"answer":"Ha, mumkin."}`)
	if ok {
		t.Fatal("a contract without confidence must not be accepted")
	}
	if parsed.Confidence >= 0.45 {
		t.Errorf("Confidence = %v, want low", parsed.Confidence)
	}
}

func TestParseAnswerClampsOutOfRange(t *testing.T) {
	high, _ := ParseAnswer(`{"answer":"x","confidence":7}`)
	if high.Confidence != 1 {
		t.Errorf("Confidence = %v, want clamp to 1", high.Confidence)
	}
	low, _ := ParseAnswer(`{"answer":"x","confidence":-3}`)
	if low.Confidence != 0 {
		t.Errorf("Confidence = %v, want clamp to 0", low.Confidence)
	}
}
