package sahiy

import "fmt"

// deliveryLabel maps a Sahiy delivery status code to a human-readable label.
// Lang values match shared.Language.Code(): uz/cyr → Uzbek Latin, ru, en, zh.
func deliveryLabel(code int, lang string) string {
	switch lang {
	case "ru":
		if l, ok := deliveryRU[code]; ok {
			return l
		}
		return fmt.Sprintf("статус %d", code)
	case "en":
		if l, ok := deliveryEN[code]; ok {
			return l
		}
		return fmt.Sprintf("status %d", code)
	case "zh":
		if l, ok := deliveryZH[code]; ok {
			return l
		}
		return fmt.Sprintf("状态 %d", code)
	default: // uz, cyr — Uzbek Latin
		if l, ok := deliveryUZ[code]; ok {
			return l
		}
		return fmt.Sprintf("holat %d", code)
	}
}

// jiyunLabel maps a Sahiy jiyun (custom) order status code to a label.
// Mirrors app/infrastructure/sahiy_api/status_maps.py jiyun_label.
func jiyunLabel(code int, lang string) string {
	switch lang {
	case "ru":
		if l, ok := jiyunRU[code]; ok {
			return l
		}
		return fmt.Sprintf("статус %d", code)
	case "en":
		if l, ok := jiyunEN[code]; ok {
			return l
		}
		return fmt.Sprintf("status %d", code)
	case "zh":
		if l, ok := jiyunZH[code]; ok {
			return l
		}
		return fmt.Sprintf("状态 %d", code)
	default:
		if l, ok := jiyunUZ[code]; ok {
			return l
		}
		return fmt.Sprintf("holat %d", code)
	}
}

// dashboardLabel maps a Sahiy dashboard (branch) status code to a label.
// Codes 2-7 collapse to a single "Delivered" label, mirroring status_maps.py.
func dashboardLabel(code int, lang string) string {
	switch code {
	case 2, 3, 4, 5, 6, 7:
		switch lang {
		case "ru":
			return "Доставлено"
		case "en":
			return "Delivered"
		case "zh":
			return "已送达"
		default:
			return "Yetkazib berilgan"
		}
	}
	switch lang {
	case "ru":
		if l, ok := dashboardRU[code]; ok {
			return l
		}
		return fmt.Sprintf("статус %d", code)
	case "en":
		return fmt.Sprintf("At branch (code %d)", code)
	case "zh":
		if l, ok := dashboardZH[code]; ok {
			return l
		}
		return fmt.Sprintf("状态 %d", code)
	default:
		if l, ok := dashboardUZ[code]; ok {
			return l
		}
		return fmt.Sprintf("holat %d", code)
	}
}

// isUnpickedDashboard reports whether a dashboard status means the parcel is
// still at the branch awaiting pickup. Mirrors status_maps.is_unpicked_dashboard.
func isUnpickedDashboard(code int) bool {
	return code == 1 || code == 8 || code == 9
}

// daigouLabel maps a Sahiy daigou (China purchase) status code to a label.
// Mirrors app/infrastructure/sahiy_api/status_maps.py daigou_label.
func daigouLabel(code int, lang string) string {
	switch lang {
	case "ru":
		if l, ok := daigouRU[code]; ok {
			return l
		}
		return fmt.Sprintf("статус %d", code)
	case "en":
		if l, ok := daigouEN[code]; ok {
			return l
		}
		return fmt.Sprintf("status %d", code)
	case "zh":
		if l, ok := daigouZH[code]; ok {
			return l
		}
		return fmt.Sprintf("状态 %d", code)
	default:
		if l, ok := daigouUZ[code]; ok {
			return l
		}
		return fmt.Sprintf("holat %d", code)
	}
}

// Status maps mirror app/infrastructure/sahiy_api/status_maps.py.
var deliveryUZ = map[int]string{
	1: "Xitoyda",
	2: "Qozog'istonda",
	3: "O'zbekistonda",
	4: "Markaziy stansiyada (olib ketish kutilmoqda)",
	5: "Pochtomatda",
	6: "Pochta/kuryer",
	7: "Yakunlangan",
	8: "Kuryerda",
}

var deliveryRU = map[int]string{
	1: "В Китае",
	2: "В Казахстане",
	3: "В Узбекистане",
	4: "На центральной станции (ожидает получения)",
	5: "В постомате",
	6: "Почта/курьер",
	7: "Завершён",
	8: "У курьера",
}

var deliveryEN = map[int]string{
	1: "In China",
	2: "In Kazakhstan",
	3: "In Uzbekistan",
	4: "At central station (awaiting pickup)",
	5: "In postmat",
	6: "Post/courier",
	7: "Completed",
	8: "With courier",
}

var deliveryZH = map[int]string{
	1: "在中国",
	2: "在哈萨克斯坦",
	3: "在乌兹别克斯坦",
	4: "在中心站（等待取货）",
	5: "在邮政柜",
	6: "邮政/快递",
	7: "已完成",
	8: "快递员处",
}

var jiyunUZ = map[int]string{
	1: "Kutilmoqda",
	2: "To'lov kutilmoqda",
	3: "Jo'natishga tayyorlanmoqda",
	4: "Jo'natilgan",
	5: "Qabul qilingan",
}

var jiyunRU = map[int]string{
	1: "Ожидается",
	2: "Ожидает оплаты",
	3: "Готовится к отправке",
	4: "Отправлен",
	5: "Принято",
}

var jiyunEN = map[int]string{
	1: "Pending",
	2: "Awaiting payment",
	3: "Preparing for shipment",
	4: "Shipped",
	5: "Received",
}

var jiyunZH = map[int]string{
	1: "等待中",
	2: "等待付款",
	3: "准备发货",
	4: "已发货",
	5: "已收货",
}

var dashboardUZ = map[int]string{
	1: "Punktda turibdi",
	8: "Qo'ng'iroq qilinmagan",
	9: "Qo'ng'iroq qilingan",
}

var dashboardRU = map[int]string{
	1: "Находится в филиале",
	8: "Не позвонили",
	9: "Позвонили",
}

var dashboardZH = map[int]string{
	1: "在取货点",
	8: "未来电",
	9: "已来电",
}

var daigouUZ = map[int]string{
	0:  "To'lov kutilmoqda",
	1:  "To'langan",
	2:  "Sotib olinmoqda",
	3:  "Sotib olingan",
	4:  "Sklatda kutilmoqda",
	5:  "Sklatda",
	6:  "Yo'lda",
	10: "Bekor qilingan",
	11: "O'chirilgan",
	12: "Muammoli buyurtma",
}

var daigouRU = map[int]string{
	0:  "Ожидает оплаты",
	1:  "Оплачено",
	2:  "Покупается",
	3:  "Куплено",
	4:  "Ожидает на складе",
	5:  "На складе",
	6:  "В пути",
	10: "Отменён",
	11: "Удалён",
	12: "Проблемный заказ",
}

var daigouEN = map[int]string{
	0:  "Awaiting payment",
	1:  "Paid",
	2:  "Being purchased",
	3:  "Purchased",
	4:  "Awaiting at warehouse",
	5:  "At warehouse",
	6:  "In transit",
	10: "Cancelled",
	11: "Deleted",
	12: "Problematic order",
}

var daigouZH = map[int]string{
	0:  "等待付款",
	1:  "已付款",
	2:  "购买中",
	3:  "已购买",
	4:  "等待入库",
	5:  "已入库",
	6:  "运输中",
	10: "已取消",
	11: "已删除",
	12: "问题订单",
}
