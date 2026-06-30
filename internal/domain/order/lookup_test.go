package order_test

import (
	"context"
	"testing"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/order"
)

type stubLookup struct {
	last order.LookupRequest
}

func (s *stubLookup) Lookup(_ context.Context, req order.LookupRequest) (order.CustomerSnapshot, error) {
	s.last = req
	return order.NewCustomerSnapshot(req.VerifiedUserID, "", req.VerifiedPhone, nil), nil
}

func TestLookupRequestCarriesVerifiedIdentity(t *testing.T) {
	stub := &stubLookup{}
	req := order.LookupRequest{
		Query:          "SF1234567890",
		VerifiedUserID: 42,
		VerifiedPhone:  "998901112233",
	}
	if _, err := stub.Lookup(context.Background(), req); err != nil {
		t.Fatal(err)
	}
	if stub.last.VerifiedUserID != 42 || stub.last.VerifiedPhone != "998901112233" {
		t.Fatalf("got %+v", stub.last)
	}
}
