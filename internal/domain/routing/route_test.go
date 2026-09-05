package routing_test

import (
	"testing"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/routing"
)

func TestIsOperatorRequest(t *testing.T) {
	if !routing.IsOperatorRequest("operator bilan bog'lanish") {
		t.Fatal("expected operator request")
	}
	if routing.IsOperatorRequest("yetkazib berish qancha vaqt") {
		t.Fatal("expected not operator request")
	}
}

func TestFallbackRouteTrack(t *testing.T) {
	got := routing.FallbackRoute("buyurtmam SF1234567890 qayerda")
	if !got.Equals(routing.RouteAPI) {
		t.Fatalf("got %s", got)
	}
}

// Without a track number the keyword router used to send order questions to
// the knowledge base. During an LLM outage that means a customer asking about
// their parcel gets an article instead of their own data.
func TestFallbackRouteOrderQuestionsWithoutTrack(t *testing.T) {
	for _, query := range []string{
		"buyurtmalarim qayerda",
		"zakazlarim",
		"buyurtmam kelmayapti",
		"где мои заказы",
		"buyurtmam qachon keladi",
	} {
		if got := routing.FallbackRoute(query); !got.Equals(routing.RouteAPI) {
			t.Errorf("FallbackRoute(%q) = %s, want api", query, got)
		}
	}
}

// The widened order rule must not swallow knowledge-base questions that merely
// mention orders.
func TestFallbackRouteKeepsFAQQuestions(t *testing.T) {
	for _, query := range []string{
		"buyurtma qanday beriladi",
		"zakaz qilish narxi qancha",
		"yetkazib berish qancha vaqt oladi",
		"ish vaqtingiz qanday",
	} {
		if got := routing.FallbackRoute(query); !got.Equals(routing.RouteFAQ) {
			t.Errorf("FallbackRoute(%q) = %s, want faq", query, got)
		}
	}
}

// An explicit operator request still outranks the order rule.
func TestFallbackRouteOperatorBeatsOrder(t *testing.T) {
	got := routing.FallbackRoute("buyurtmam qayerda, operator bilan bog'lang")
	if !got.Equals(routing.RouteTicket) {
		t.Fatalf("got %s, want ticket", got)
	}
}

func TestFallbackRouteChitchat(t *testing.T) {
	if !routing.FallbackRoute("salom").Equals(routing.RouteChitchat) {
		t.Fatal("expected chitchat")
	}
}

func TestParseRoute(t *testing.T) {
	if !routing.ParseRoute("product_search").Equals(routing.RouteProductSearch) {
		t.Fatal("parse product_search")
	}
	if !routing.ParseRoute("unknown").Equals(routing.RouteFAQ) {
		t.Fatal("unknown defaults to faq")
	}
}
