package order

import "github.com/sahiy-backend/sahiy-agent/internal/domain/shared"

// LogisticsStatus is Sahiy's unified 1-12 delivery-stage code. Each order
// source (delivery, daigou, jiyun) reports its own status codes; this is the
// single scale ETA math is defined against. 12 means delivered.
type LogisticsStatus int

// StageDelivered is the terminal stage: the parcel has reached the customer.
const StageDelivered LogisticsStatus = 12

// logisticsDefaultDays is the typical number of days a parcel spends in each
// stage, used to sum a remaining-time estimate. Stage 12 (delivered) has
// nothing further to add and so carries no entry.
var logisticsDefaultDays = map[LogisticsStatus]int{
	1: 1, 2: 3, 3: 1, 4: 4, 5: 5, 6: 1, 7: 1, 8: 1, 9: 2, 10: 1, 11: 3,
}

// logisticsStatusLabels are per-language display labels for each stage,
// keyed by shared.Language code (uz, cyr, ru, en, zh).
var logisticsStatusLabels = map[LogisticsStatus]map[string]string{
	1:  {"uz": "Sotib olindi", "cyr": "Сотиб олинди", "ru": "Куплено", "en": "Purchased", "zh": "已购买"},
	2:  {"uz": "Omborga yo'lda", "cyr": "Омборга йўлда", "ru": "В пути на склад", "en": "On the way to warehouse", "zh": "运往仓库途中"},
	3:  {"uz": "Sahiy (Xitoy) omborida", "cyr": "Сахий (Хитой) омборида", "ru": "На складе Sahiy (Китай)", "en": "At Sahiy warehouse (China)", "zh": "Sahiy中国仓库"},
	4:  {"uz": "Qirg'izistonga yo'lda", "cyr": "Қирғизистонга йўлда", "ru": "В пути в Кыргызстан", "en": "On the way to Kyrgyzstan", "zh": "运往吉尔吉斯斯坦途中"},
	5:  {"uz": "O'zbekistonga yo'lda", "cyr": "Ўзбекистонга йўлда", "ru": "В пути в Узбекистан", "en": "On the way to Uzbekistan", "zh": "运往乌兹别克斯坦途中"},
	6:  {"uz": "Toshkentda", "cyr": "Тошкентда", "ru": "В Ташкенте", "en": "In Tashkent", "zh": "在塔什干"},
	7:  {"uz": "Markaziy punktda", "cyr": "Марказий пунктда", "ru": "На центральном пункте", "en": "At central pickup point", "zh": "在中央取货点"},
	8:  {"uz": "Mijozga kuryerda", "cyr": "Мижозга курьерда", "ru": "Курьер везёт клиенту", "en": "Courier to customer", "zh": "快递员配送中"},
	9:  {"uz": "Markaziy punktga kuryerda", "cyr": "Марказий пунктга курьерда", "ru": "Курьер везёт на пункт", "en": "Courier to pickup point", "zh": "送往取货点途中"},
	10: {"uz": "Postomatga kuryerda", "cyr": "Постоматга курьерда", "ru": "Курьер везёт в постомат", "en": "Courier to locker", "zh": "送往自取柜途中"},
	11: {"uz": "Postomatda", "cyr": "Постоматда", "ru": "В постомате", "en": "In pickup locker", "zh": "在自取柜"},
	12: {"uz": "Yetkazildi", "cyr": "Етказилди", "ru": "Доставлено", "en": "Delivered", "zh": "已送达"},
}

// Source-specific status code -> unified logistics stage. Only delivery and
// daigou are populated with real data today (see CustomerAPI); jiyun is kept
// so the table is ready once that source is fetched.
var (
	daigouToLogistics   = map[int]LogisticsStatus{0: 1, 1: 1, 2: 2, 3: 1, 4: 2, 5: 3, 6: 4}
	jiyunToLogistics    = map[int]LogisticsStatus{1: 3, 2: 3, 3: 3, 4: 4, 5: 12}
	deliveryToLogistics = map[int]LogisticsStatus{1: 3, 2: 4, 3: 5, 4: 7, 5: 11, 6: 9, 7: 12, 8: 8}
)

// ResolveLogisticsStatus maps a source's own status code to the unified 1-12
// stage. ok is false when the source or code has no known mapping.
func ResolveLogisticsStatus(source string, statusCode int) (LogisticsStatus, bool) {
	var table map[int]LogisticsStatus
	switch source {
	case SourceDaigou:
		table = daigouToLogistics
	case SourceJiyun:
		table = jiyunToLogistics
	case SourceDelivery, SourceUnpicked:
		table = deliveryToLogistics
	default:
		return 0, false
	}
	stage, ok := table[statusCode]
	return stage, ok
}

// EstimateRemainingDays sums the default days for every stage from status up
// to (but excluding) delivered. A status at or past delivered costs nothing
// more; a status below the first stage is clamped up to it.
func EstimateRemainingDays(status LogisticsStatus) int {
	if status >= StageDelivered {
		return 0
	}
	if status < 1 {
		status = 1
	}
	total := 0
	for step := status; step < StageDelivered; step++ {
		total += logisticsDefaultDays[step]
	}
	return total
}

// LogisticsStatusLabel returns the display label for a stage in lang, falling
// back to Uzbek Latin for an unrecognized language or stage.
func LogisticsStatusLabel(status LogisticsStatus, lang shared.Language) string {
	labels, ok := logisticsStatusLabels[status]
	if !ok {
		return ""
	}
	if l, ok := labels[lang.Code()]; ok && l != "" {
		return l
	}
	return labels[shared.LangUz.Code()]
}

// ETA is a computed delivery estimate for one order.
type ETA struct {
	Status        LogisticsStatus
	StatusLabel   string
	RemainingDays int
	Delivered     bool
}

// EstimateETA computes the delivery estimate for an order. ok is false when
// the order's source/status code has no known logistics mapping (e.g. an
// unrecognized status), in which case no ETA can be honestly given.
func EstimateETA(o Order, lang shared.Language) (ETA, bool) {
	status, ok := ResolveLogisticsStatus(o.Source(), o.StatusCode())
	if !ok {
		return ETA{}, false
	}
	if status >= StageDelivered {
		return ETA{Status: status, StatusLabel: LogisticsStatusLabel(status, lang), Delivered: true}, true
	}
	return ETA{
		Status:        status,
		StatusLabel:   LogisticsStatusLabel(status, lang),
		RemainingDays: EstimateRemainingDays(status),
	}, true
}
