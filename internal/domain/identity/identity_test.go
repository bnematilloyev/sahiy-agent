package identity

import (
	"testing"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
)

func TestExtractSahiyUserID(t *testing.T) {
	tests := []struct {
		in   string
		want int64
	}{
		{"111111", 111111},
		{"id 191052", 191052},
		{"773402738804490", 0},
	}
	for _, tc := range tests {
		if got := ExtractSahiyUserID(tc.in); got != tc.want {
			t.Fatalf("ExtractSahiyUserID(%q) = %d, want %d", tc.in, got, tc.want)
		}
	}
}

func TestValidateUzbekPhone(t *testing.T) {
	if got := ValidateUzbekPhone("+998 90 123 45 67"); got != "998901234567" {
		t.Fatalf("ValidateUzbekPhone = %q", got)
	}
	if got := ValidateUzbekPhone("123"); got != "" {
		t.Fatalf("expected invalid phone, got %q", got)
	}
}

func TestFromMessages(t *testing.T) {
	sid := conversation.NewSessionID()
	now := time.Now()
	msgs := []conversation.Message{
		conversation.ReconstituteMessage(conversation.NewMessageID(), sid, conversation.RoleUser, PhoneMessagePrefix+"998901112233", "", now),
		conversation.ReconstituteMessage(conversation.NewMessageID(), sid, conversation.RoleUser, SahiyUserMessagePrefix+"7991625", "", now),
	}
	id := FromMessages(msgs)
	if id.Phone != "998901112233" {
		t.Fatalf("phone = %q", id.Phone)
	}
	if id.SahiyUserID != 7991625 {
		t.Fatalf("sahiy_user_id = %d", id.SahiyUserID)
	}
}

func TestIsIdentityOnlyMessage(t *testing.T) {
	if !IsIdentityOnlyMessage("111111") {
		t.Fatal("expected identity-only for sahiy id")
	}
	if IsIdentityOnlyMessage("buyurtam qayerda") {
		t.Fatal("expected not identity-only")
	}
}

func TestRequiresCustomerIdentity(t *testing.T) {
	if !RequiresCustomerIdentity("telegram") {
		t.Fatal("telegram requires identity")
	}
	if RequiresCustomerIdentity("api") {
		t.Fatal("api should not require identity")
	}
}
