package order

import (
	"testing"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

func TestIsListQuestion(t *testing.T) {
	cases := []struct {
		query string
		want  bool
	}{
		{"buyurtmalarim qayerda", true},
		{"zakazlarim", true},
		{"barcha buyurtmalarim", true},
		{"buyurtmam holati qanday", true},
		{"мои заказы", true},
		{"где мои посылки", true},
		{"покажи заказы", true},

		// A named parcel is a single-order question, not a list.
		{"SF1234567890 qayerda", false},
		// Ordinary knowledge-base questions must not look like list questions.
		{"buyurtma qanday beriladi", false},
		{"salom", false},
		{"", false},
	}
	for _, c := range cases {
		if got := IsListQuestion(c.query); got != c.want {
			t.Errorf("IsListQuestion(%q) = %v, want %v", c.query, got, c.want)
		}
	}
}

func TestIsLookupRequest(t *testing.T) {
	cases := []struct {
		name  string
		query string
		want  bool
	}{
		{"track number", "SF1234567890", true},
		{"list question", "buyurtmalarim qayerda", true},
		{"delay complaint", "buyurtmam kelmayapti", true},
		{"russian delay", "заказ задержка", true},
		{"noun plus status", "zakaz holati", true},
		{"noun plus arrival", "buyurtmam qachon keladi", true},
		{"russian where", "где мой заказ", true},

		// Mentions orders, but asks how the service works: knowledge base.
		{"how to order", "buyurtma qanday beriladi", false},
		{"order price question", "zakaz qilish narxi qancha", false},
		{"greeting", "salom", false},
		{"unrelated", "ish vaqtingiz qanday", false},
		{"empty", "", false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := IsLookupRequest(c.query); got != c.want {
				t.Errorf("IsLookupRequest(%q) = %v, want %v", c.query, got, c.want)
			}
		})
	}
}

func TestMergeFollowUpRecoversTrackFromEarlierTurn(t *testing.T) {
	history := []string{
		"salom",
		"SF1234567890 qayerda",
		"rahmat",
	}

	got := MergeFollowUp("bu chi?", history)

	if got == "bu chi?" {
		t.Fatal("a bare follow-up should have been merged with the earlier track")
	}
	if _, ok := shared.ExtractTrack(got); !ok {
		t.Fatalf("merged query carries no track: %q", got)
	}
}

func TestMergeFollowUpUsesMostRecentTrack(t *testing.T) {
	history := []string{"SF1111111111 holati", "SF2222222222 holati"}

	got := MergeFollowUp("unda?", history)

	if track, _ := shared.ExtractTrack(got); track != "SF2222222222" {
		t.Errorf("merged with %q, want the most recent track SF2222222222", got)
	}
}

func TestMergeFollowUpLeavesSelfContainedMessages(t *testing.T) {
	history := []string{"SF1111111111 holati"}

	// Already names its own parcel: nothing to recover.
	if got := MergeFollowUp("SF2222222222 chi?", history); got != "SF2222222222 chi?" {
		t.Errorf("a message with its own track must not be merged, got %q", got)
	}
	// Not a follow-up at all.
	if got := MergeFollowUp("buyurtmalarim qayerda", history); got != "buyurtmalarim qayerda" {
		t.Errorf("a standalone question must not be merged, got %q", got)
	}
}

func TestMergeFollowUpWithoutAnyEarlierTrack(t *testing.T) {
	if got := MergeFollowUp("bu chi?", []string{"salom", "rahmat"}); got != "bu chi?" {
		t.Errorf("with no track in history the text must be left alone, got %q", got)
	}
	if got := MergeFollowUp("bu chi?", nil); got != "bu chi?" {
		t.Errorf("with no history the text must be left alone, got %q", got)
	}
}

// The hint words must match as words, not as fragments of longer ones.
func TestMergeFollowUpIgnoresHintsInsideWords(t *testing.T) {
	history := []string{"SF1234567890 holati"}
	// "chidab" and "hammasi" merely contain the hint letters.
	for _, text := range []string{"chidab turaman", "hammasi joyidami"} {
		if got := MergeFollowUp(text, history); got != text {
			t.Errorf("MergeFollowUp(%q) merged on a substring match: %q", text, got)
		}
	}
}
