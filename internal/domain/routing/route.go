// Package routing is the bounded context for deciding which processing path a
// user message takes. It holds the Route value object and pure classification
// logic; the LLM-assisted decision lives in the application layer.
package routing

import "github.com/sahiy-backend/sahiy-agent/internal/domain/shared"

// Route is the value object naming a processing path.
type Route struct {
	value string
}

// Known routes handled by RouterResponder and its optional handlers.
var (
	RouteFAQ           = Route{value: "faq"}
	RouteAPI           = Route{value: "api"}
	RouteTicket        = Route{value: "ticket"}
	RoutePickup        = Route{value: "pickup"}
	RouteProductSearch = Route{value: "product_search"}
	RouteCategory      = Route{value: "category"}
	RouteChitchat      = Route{value: "chitchat"}
)

// ParseRoute maps a raw string (e.g. from LLM JSON) to a Route, defaulting to
// FAQ when unrecognized.
func ParseRoute(raw string) Route {
	switch raw {
	case RouteAPI.value:
		return RouteAPI
	case RouteTicket.value:
		return RouteTicket
	case RoutePickup.value:
		return RoutePickup
	case RouteProductSearch.value:
		return RouteProductSearch
	case RouteCategory.value:
		return RouteCategory
	case RouteChitchat.value:
		return RouteChitchat
	default:
		return RouteFAQ
	}
}

// String returns the route name.
func (r Route) String() string { return r.value }

// Equals reports route equality.
func (r Route) Equals(other Route) bool { return r.value == other.value }

// Decision is the outcome of routing: which path, the resolved reply language,
// and an optional extracted search query (for product search).
type Decision struct {
	Route       Route
	Language    shared.Language
	SearchQuery string
}
