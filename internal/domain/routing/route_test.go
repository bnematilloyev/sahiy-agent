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
