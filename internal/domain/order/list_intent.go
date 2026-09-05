package order

import (
	"sort"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// RowFilter narrows an order list to a lifecycle slice the customer asked
// about ("cancelled orders", "what is still on the way").
type RowFilter string

// Recognized row filters. FilterNone means the customer did not narrow by
// status, so every row of the selected sources is kept.
const (
	FilterNone           RowFilter = ""
	FilterCancelled      RowFilter = "cancelled"
	FilterActive         RowFilter = "active"
	FilterPendingArrival RowFilter = "pending_arrival"
	FilterCompleted      RowFilter = "completed"
	FilterDelayed        RowFilter = "delayed"
	FilterInChina        RowFilter = "in_china"
)

// allSources is every order source the Sahiy API exposes; it is also the
// default set, used when the customer names no particular one.
var allSources = []string{SourceDelivery, SourceDaigou, SourceDashboard, SourceJiyun, SourceUnpicked}

// ListIntent is what an order-list question asks for: which sources to query
// and which rows within them are relevant.
//
// It is resolved before any API call, because the source set decides which
// endpoints are worth hitting at all - that decision cannot be delegated to
// the model, which only ever sees data that was already fetched.
type ListIntent struct {
	sources          map[string]bool
	rowFilter        RowFilter
	includeCompleted bool
}

// DefaultListIntent asks every source for every row.
func DefaultListIntent() ListIntent {
	return ListIntent{sources: sourceSet(allSources...)}
}

func sourceSet(names ...string) map[string]bool {
	out := make(map[string]bool, len(names))
	for _, n := range names {
		out[n] = true
	}
	return out
}

// WantsSource reports whether this source should be queried and kept.
func (i ListIntent) WantsSource(source string) bool {
	if len(i.sources) == 0 {
		return true
	}
	return i.sources[source]
}

// Sources lists the wanted sources in a stable order.
func (i ListIntent) Sources() []string {
	out := make([]string, 0, len(i.sources))
	for s := range i.sources {
		out = append(out, s)
	}
	sort.Strings(out)
	return out
}

// RowFilter returns the lifecycle filter, or FilterNone.
func (i ListIntent) RowFilter() RowFilter { return i.rowFilter }

// IncludeCompleted reports that the customer explicitly asked for *all* their
// orders, so finished ones should not be hidden. It only ever holds when no
// row filter applies. Consumed by order chaining (not yet ported), which
// otherwise drops delivered rows to keep the list short.
func (i ListIntent) IncludeCompleted() bool { return i.includeCompleted }

// IsDefault reports whether the question narrowed nothing.
func (i ListIntent) IsDefault() bool {
	return i.rowFilter == FilterNone && !i.includeCompleted && len(i.sources) == len(allSources)
}

// ScopeDescription describes the applied narrowing in English, for the LLM
// context. It deliberately does not localize: like the rest of Summarize, the
// model translates it into the customer's language itself.
func (i ListIntent) ScopeDescription() string {
	if i.IsDefault() {
		return ""
	}
	var parts []string
	switch i.rowFilter {
	case FilterCancelled:
		parts = append(parts, "cancelled orders")
	case FilterActive:
		parts = append(parts, "active (not yet finished) orders")
	case FilterPendingArrival:
		parts = append(parts, "orders still on the way")
	case FilterCompleted:
		parts = append(parts, "completed orders")
	case FilterDelayed:
		parts = append(parts, "delayed or not-yet-collected orders")
	case FilterInChina:
		parts = append(parts, "orders still at the China stage")
	}
	if len(i.sources) != len(allSources) {
		parts = append(parts, "sources: "+strings.Join(i.Sources(), ", "))
	}
	if len(parts) == 0 {
		return ""
	}
	return "The customer asked about: " + strings.Join(parts, "; ") + "."
}

// Keyword rules are matched against shared.NormalizeForMatch output. Russian
// terms are written in Cyrillic on purpose: normalizeAll puts them through the
// very same normalizer as the incoming message, so the two can never drift
// apart the way a hand-written transliteration would (the Python original
// stored pre-transliterated forms such as "zaderzhka", which this codebase's
// normalizer renders "zaderjka" - a silent mismatch).
var (
	daigouKeywords = normalizeAll(
		"daigou", "daigo", "dg zakaz",
		"xitoy", "xitoyda", "xitoydagi", "omborda", "ombor", "sotib olin",
		"китай", "китайск", "склад китай", "закуп", "скупка",
	)
	deliveryKeywords = normalizeAll(
		"yetkazib", "yetkazish", "delivery", "kuryer", "pochta", "yurt ich", "logistika",
		"доставка", "курьер", "почта",
	)
	unpickedKeywords = normalizeAll(
		"olib ketilmagan", "olib kelmagan", "olib kelinmagan",
		"markaziy stansiya", "stansiyada", "punktga kelmagan",
		"не получено", "не забрал", "не забрана", "ждет в пункте",
	)
	dashboardKeywords = normalizeAll(
		"filialda", "punktda", "filial punkt",
		"в филиале", "в пункте",
	)
	jiyunKeywords = normalizeAll("jiyun")

	cancelledKeywords = normalizeAll(
		"bekor", "bekorlangan", "bekor qilingan", "bekor bolgan",
		"cancel", "cancelled",
		"отмен",
	)
	activeKeywords = normalizeAll(
		"aktiv", "faol", "ochiq", "jarayonda", "davom et",
		"active", "my active",
		"актив", "текущие", "открыт",
	)
	completedKeywords = normalizeAll(
		"yakunlangan", "tugagan", "yetkazilgan", "olib ketilgan",
		"qabul qilingan", "qabul qilgan", "qabul qilib olgan", "qabul qilib",
		"received order", "completed order",
		"заверш", "получен", "получил", "закрыт",
	)
	delayedKeywords = normalizeAll(
		"kelmayapti", "kelmay", "kelmagan", "kemayapti", "kemay", "kemagan",
		"yetkazilmagan", "yetkazilmadi", "kechik",
		"не пришел", "не приехало", "задержк", "задержалась", "опоздание",
	)
	inChinaKeywords = normalizeAll(
		"xitoyda", "xitoydagi", "xitoy ombor",
		"в китае", "из китая", "китайский склад",
	)
	arrivalKeywords = normalizeAll(
		"qachon keladi", "qachon kelad", "qachon yetkaziladi", "qachon yetib keladi",
		"qachon olaman", "qachon boradi",
		"когда придет", "когда прийдет",
		"when will it arrive", "when will my order arrive", "when will my package arrive",
	)
	// arrivalContext keeps a bare "when will it come" from being read as an
	// order question when nothing in the message refers to an order.
	arrivalContextWords = normalizeAll(
		"tovar", "tovarim", "tovarlar", "buyurtma", "buyurtmam", "mahsulot",
		"заказ", "посылк", "товар",
	)
	arrivalVerbs      = normalizeAll("keladi", "kelad", "arrive", "yetkaz", "придет", "прийдет")
	arrivalAsks       = normalizeAll("qachon", "when", "когда")
	allOrdersKeywords = normalizeAll(
		"hammasi", "hamma zakaz", "barcha buyurtma", "buyurtmalarim holati",
		"all order", "all orders",
		"все заказ", "все товары",
	)
	whereWords     = normalizeAll("qayerda", "qayda", "where", "где")
	orderNounWords = normalizeAll("zakaz", "order", "buyurtma", "tovar", "posylk", "mani", "moi", "my ", "заказ", "товар", "посылк", "мои")
	acceptedPhrase = shared.NormalizeForMatch("qabul qil")
)

func normalizeAll(phrases ...string) []string {
	out := make([]string, len(phrases))
	for i, p := range phrases {
		out[i] = shared.NormalizeForMatch(p)
	}
	return out
}

func containsAny(text string, phrases []string) bool {
	for _, p := range phrases {
		if p != "" && strings.Contains(text, p) {
			return true
		}
	}
	return false
}

// ParseListIntent decides which sources and which rows an order-list question
// is about. An unrecognized question yields DefaultListIntent.
func ParseListIntent(text string) ListIntent {
	lowered := shared.NormalizeForMatch(text)
	if lowered == "" {
		return DefaultListIntent()
	}

	includeCompleted := containsAny(lowered, allOrdersKeywords)

	// First match wins: the filters are ordered from most specific ("cancelled")
	// to most general ("completed"), so a message that trips several rules is
	// read as the narrower one.
	rowFilter := FilterNone
	switch {
	case containsAny(lowered, cancelledKeywords):
		rowFilter = FilterCancelled
	case containsAny(lowered, delayedKeywords):
		rowFilter = FilterDelayed
	case isPendingArrivalQuestion(lowered):
		rowFilter = FilterPendingArrival
	case containsAny(lowered, activeKeywords):
		rowFilter = FilterActive
	case isWhereOrdersQuestion(lowered):
		// "where are my orders" is a status question about live orders.
		rowFilter = FilterActive
	case containsAny(lowered, inChinaKeywords):
		rowFilter = FilterInChina
	case isCompletedOrdersQuestion(lowered):
		rowFilter = FilterCompleted
	}

	wantDaigou := containsAny(lowered, daigouKeywords)
	wantDelivery := containsAny(lowered, deliveryKeywords)
	wantUnpicked := containsAny(lowered, unpickedKeywords)
	wantDashboard := containsAny(lowered, dashboardKeywords)
	wantJiyun := containsAny(lowered, jiyunKeywords)

	// These two filters imply their sources even when the customer named none.
	if rowFilter == FilterDelayed {
		wantUnpicked, wantDelivery = true, true
	}
	if rowFilter == FilterInChina {
		wantDaigou, wantDelivery = true, true
	}

	var sources map[string]bool
	switch {
	case wantDaigou || wantDelivery || wantUnpicked || wantDashboard || wantJiyun:
		sources = map[string]bool{}
		for source, wanted := range map[string]bool{
			SourceDaigou:    wantDaigou,
			SourceDelivery:  wantDelivery,
			SourceUnpicked:  wantUnpicked,
			SourceDashboard: wantDashboard,
			SourceJiyun:     wantJiyun,
		} {
			if wanted {
				sources[source] = true
			}
		}
	case rowFilter == FilterCancelled:
		// Only purchase and logistics rows can be cancelled.
		sources = sourceSet(SourceDaigou, SourceJiyun)
	case rowFilter == FilterActive, rowFilter == FilterPendingArrival:
		sources = sourceSet(SourceDaigou, SourceJiyun)
	case rowFilter == FilterCompleted:
		sources = sourceSet(SourceJiyun, SourceDelivery, SourceDaigou)
	default:
		sources = sourceSet(allSources...)
	}

	return ListIntent{
		sources:   sources,
		rowFilter: rowFilter,
		// "Show me everything" only means anything when no narrower filter won.
		includeCompleted: includeCompleted && rowFilter == FilterNone,
	}
}

// isWhereOrdersQuestion matches "where are my orders" - a "where" word plus
// something that refers to an order, so a bare "where?" does not qualify.
func isWhereOrdersQuestion(lowered string) bool {
	return containsAny(lowered, whereWords) && containsAny(lowered, orderNounWords)
}

// isCompletedOrdersQuestion also accepts the Uzbek "qabul qil-" stem, which
// only means "received" when paired with an order noun ("qabul qilgan
// buyurtmalarim") - on its own it is an ordinary verb.
func isCompletedOrdersQuestion(lowered string) bool {
	if containsAny(lowered, completedKeywords) {
		return true
	}
	return strings.Contains(lowered, acceptedPhrase) && containsAny(lowered, orderNounWords)
}

// isPendingArrivalQuestion matches "when will it arrive". A full phrase is
// enough on its own; otherwise the message must combine an asking word, an
// arrival verb and an order noun, so "when do you open" does not qualify.
func isPendingArrivalQuestion(lowered string) bool {
	if containsAny(lowered, arrivalKeywords) {
		return true
	}
	return containsAny(lowered, arrivalAsks) &&
		containsAny(lowered, arrivalVerbs) &&
		containsAny(lowered, arrivalContextWords)
}

// isUnpickedDashboard reports whether a dashboard status means the parcel is
// still at the branch awaiting pickup.
func isUnpickedDashboard(code int) bool {
	return code == 1 || code == 8 || code == 9
}

// MatchesFilter reports whether an order belongs in a filtered list.
//
// The rules are per-source because the same integer means different things in
// each pipeline: delivery 7 is "completed" while daigou 7 is not, and daigou 6
// ("in transit") is deliberately dropped from active lists because that parcel
// already appears as a jiyun/delivery row.
func MatchesFilter(o Order, filter RowFilter) bool {
	if filter == FilterNone {
		return true
	}
	code := o.StatusCode()
	switch filter {
	case FilterCancelled:
		return o.Source() == SourceDaigou && (code == 10 || code == 11)

	case FilterCompleted:
		switch o.Source() {
		case SourceDelivery, SourceUnpicked:
			return code == 7
		case SourceDaigou:
			return code == 6 || code == 7
		case SourceDashboard:
			return code >= 2 && code <= 7
		case SourceJiyun:
			return code == 5
		}
		return false

	case FilterActive, FilterPendingArrival:
		switch o.Source() {
		case SourceDaigou:
			return code != 6 && code != 10 && code != 11
		case SourceDelivery:
			return code != 7
		case SourceUnpicked:
			return true
		case SourceDashboard:
			return isUnpickedDashboard(code)
		case SourceJiyun:
			return code != 5
		}
		return true

	case FilterDelayed:
		switch o.Source() {
		case SourceUnpicked:
			return true
		case SourceDelivery:
			// 4 = sitting at the central station, the state a customer means by
			// "it never arrived".
			return code == 4
		}
		return false

	case FilterInChina:
		switch o.Source() {
		case SourceDelivery:
			return code == 1 || code == 2
		case SourceDaigou:
			return code >= 0 && code <= 5
		}
		return false
	}
	return true
}

// ApplyListIntent drops sources the question did not ask for and rows that do
// not match its filter. The daigou total is recomputed from what survives, so
// it never advertises more orders than the list shows.
func ApplyListIntent(s CustomerSnapshot, intent ListIntent) CustomerSnapshot {
	keep := func(source string, orders []Order) []Order {
		if !intent.WantsSource(source) {
			return nil
		}
		if intent.RowFilter() == FilterNone {
			return orders
		}
		out := make([]Order, 0, len(orders))
		for _, o := range orders {
			if MatchesFilter(o, intent.RowFilter()) {
				out = append(out, o)
			}
		}
		if len(out) == 0 {
			return nil
		}
		return out
	}

	out := s
	out.orders = keep(SourceDelivery, s.orders)
	out.jiyunOrders = keep(SourceJiyun, s.jiyunOrders)
	out.dashboardOrders = keep(SourceDashboard, s.dashboardOrders)
	out.unpickedOrders = keep(SourceUnpicked, s.unpickedOrders)
	out.daigouOrders = keep(SourceDaigou, s.daigouOrders)
	if len(out.daigouOrders) != len(s.daigouOrders) {
		out.daigouTotal = len(out.daigouOrders)
	}
	out.scope = intent.ScopeDescription()
	return out
}
