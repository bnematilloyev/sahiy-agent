package chat

import (
	"context"
	"io"
	"log/slog"
	"strings"
	"testing"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
	"github.com/sahiy-backend/sahiy-agent/internal/app/faq"
	"github.com/sahiy-backend/sahiy-agent/internal/app/router"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/knowledge"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

const testEscalationThreshold = 0.45

// stubCompleter answers router prompts and customer prompts differently, so one
// fake can serve a full Respond round-trip.
type stubCompleter struct {
	answer    ai.Completion
	available bool
}

func (c stubCompleter) Available() bool { return c.available }

func (c stubCompleter) Complete(_ context.Context, req ai.CompletionRequest) (ai.Completion, error) {
	if strings.Contains(req.System, "Routes:") {
		if c.answer.Degraded {
			return ai.Completion{Degraded: true}, nil
		}
		return ai.Completion{Text: `{"route":"faq","reply_language":"uz","search_query":""}`}, nil
	}
	return c.answer, nil
}

// emptyRepo forces the generic (non-RAG) answer path.
type emptyRepo struct{}

func (emptyRepo) SearchByVector(context.Context, []float32, int) ([]knowledge.SearchResult, error) {
	return nil, nil
}

func (emptyRepo) SearchByKeyword(context.Context, string, int) ([]knowledge.SearchResult, error) {
	return nil, nil
}

type stubEmbedder struct{}

func (stubEmbedder) Embed(context.Context, string) (ai.Embedding, error) {
	return ai.Embedding{Vector: []float32{0.1}}, nil
}

func newTestResponder(t *testing.T, answer ai.Completion) *RouterResponder {
	t.Helper()
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	completer := stubCompleter{answer: answer, available: !answer.Degraded}
	faqSvc := faq.New(emptyRepo{}, nil, stubEmbedder{}, completer, faq.Config{Threshold: 0.85, TopK: 3}, log)
	return NewRouterResponder(router.New(completer, log), faqSvc, Handlers{}, testEscalationThreshold, log)
}

func newTestSession(t *testing.T) *conversation.Session {
	t.Helper()
	uid, err := shared.NewUserID("u-1")
	if err != nil {
		t.Fatalf("NewUserID: %v", err)
	}
	return conversation.Open(uid, conversation.NewChannel("telegram"))
}

// The regression this whole change exists for: a model that admits it does not
// know must reach a human, not be shown to the customer as a final answer.
func TestRespondEscalatesOnLowConfidence(t *testing.T) {
	responder := newTestResponder(t, ai.Completion{
		Text: `{"answer":"Bu haqda aniq ma'lumotim yo'q.","confidence":0.2}`,
	})

	out, err := responder.Respond(context.Background(), newTestSession(t), "kafolat qancha muddat?", nil)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if !out.Escalate {
		t.Error("Escalate = false, want true for a 0.2-confidence answer")
	}
	if out.HandoffReason != shared.HandoffLowConfidence {
		t.Errorf("HandoffReason = %v, want low confidence", out.HandoffReason)
	}
	if !strings.Contains(out.Text, "operator") {
		t.Errorf("Text = %q, want an operator handoff notice appended", out.Text)
	}
}

func TestRespondKeepsConfidentAnswer(t *testing.T) {
	responder := newTestResponder(t, ai.Completion{
		Text: `{"answer":"Yetkazib berish 7-10 kun.","confidence":0.95}`,
	})

	out, err := responder.Respond(context.Background(), newTestSession(t), "yetkazib berish qancha vaqt?", nil)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if out.Escalate {
		t.Error("Escalate = true, want false for a confident answer")
	}
	if out.Text != "Yetkazib berish 7-10 kun." {
		t.Errorf("Text = %q, want the model answer unwrapped from the contract", out.Text)
	}
}

// With every provider down the assistant is blind. It must hand off instead of
// showing the internal fallback placeholder to the customer.
func TestRespondEscalatesWhenAllProvidersDegraded(t *testing.T) {
	responder := newTestResponder(t, ai.Completion{Text: "AI providers unavailable", Degraded: true})

	out, err := responder.Respond(context.Background(), newTestSession(t), "kafolat qancha muddat?", nil)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if !out.Escalate {
		t.Error("Escalate = false, want true in degraded mode")
	}
	if strings.Contains(out.Text, "unavailable") {
		t.Errorf("Text = %q, internal placeholder leaked to the customer", out.Text)
	}
	if out.Type != conversation.MessageTypeTicket {
		t.Errorf("Type = %v, want ticket", out.Type)
	}
}

// Small talk does not need a human even when the models are down.
func TestRespondAnswersGreetingWithoutOperatorWhenDegraded(t *testing.T) {
	responder := newTestResponder(t, ai.Completion{Text: "AI providers unavailable", Degraded: true})

	out, err := responder.Respond(context.Background(), newTestSession(t), "salom", nil)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if out.Escalate {
		t.Error("Escalate = true, a greeting should not reach an operator")
	}
	if !strings.Contains(strings.ToLower(out.Text), "assalomu alaykum") {
		t.Errorf("Text = %q, want a deterministic greeting", out.Text)
	}
}

// An insult is answered with a civility reminder without spending a model call.
func TestRespondAnswersProfanityWithCivilityReminder(t *testing.T) {
	responder := newTestResponder(t, ai.Completion{
		Text: `{"answer":"MODEL ANSWER","confidence":0.9}`,
	})

	out, err := responder.Respond(context.Background(), newTestSession(t), "sen ahmoq ekansan", nil)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if out.Text == "MODEL ANSWER" {
		t.Error("an insult must not reach the model")
	}
	if !strings.Contains(out.Text, "hurmat") {
		t.Errorf("Text = %q, want a civility reminder", out.Text)
	}
	if out.Escalate {
		t.Error("Escalate = true, an insult alone should not open a ticket")
	}
}

// An angry customer who still asks for a human must get one: the operator
// branch is checked before the civility reminder.
func TestRespondPrefersOperatorRequestOverProfanity(t *testing.T) {
	responder := newTestResponder(t, ai.Completion{Text: `{"answer":"x","confidence":0.9}`})

	out, err := responder.Respond(context.Background(), newTestSession(t), "ahmoq bot, operator chaqir", nil)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if !out.Escalate {
		t.Error("Escalate = false, want the operator request to win over the insult")
	}
}

// Every outcome must carry how it was produced, because ReplyService records
// the turn from these fields alone and cannot re-derive them.
func TestRespondStampsRouteAndLanguage(t *testing.T) {
	responder := newTestResponder(t, ai.Completion{
		Text: `{"answer":"Yetkazish 7-14 kun.","confidence":0.9}`,
	})
	session := conversation.Open(mustUserID(t, "u1"), conversation.ChannelTelegram)

	out, err := responder.Respond(context.Background(), session, "yetkazish qancha vaqt", nil)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if out.Route == "" {
		t.Error("Route was not stamped on the outcome")
	}
	if out.Language == "" {
		t.Error("Language was not stamped on the outcome")
	}
	if out.Degraded {
		t.Error("a real model answered, so Degraded must be false")
	}
}

// When no model answered, the outcome has to say so: a low confidence alone
// cannot distinguish "unsure" from "blind".
func TestRespondMarksDegradedWhenNoModelAnswered(t *testing.T) {
	responder := newTestResponder(t, ai.Completion{Degraded: true})
	session := conversation.Open(mustUserID(t, "u1"), conversation.ChannelTelegram)

	out, err := responder.Respond(context.Background(), session, "yetkazish qancha vaqt", nil)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if !out.Degraded {
		t.Error("expected Degraded to be set when every provider was unavailable")
	}
	if out.Route == "" {
		t.Error("a degraded outcome still needs its route recorded")
	}
}

func mustUserID(t *testing.T, raw string) shared.UserID {
	t.Helper()
	id, err := shared.NewUserID(raw)
	if err != nil {
		t.Fatalf("NewUserID: %v", err)
	}
	return id
}
