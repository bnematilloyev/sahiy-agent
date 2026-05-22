"""Human-readable labels for Sahiy order status codes (RAG context)."""

from __future__ import annotations

# ── O'zbek lotin ───────────────────────────────────────────────────────────
DELIVERY_STATUS: dict[int, str] = {
    1: "Xitoyda",
    2: "Qozog'istonda",
    3: "O'zbekistonda",
    4: "Markaziy stansiyada (olib ketish kutilmoqda)",
    5: "Pochtomatda",
    6: "Pochta/kuryer",
    7: "Yakunlangan",
    8: "Kuryerda",
}

DASHBOARD_STATUS: dict[int, str] = {
    1: "Punktda turibdi",
    8: "Qo'ng'iroq qilinmagan",
    9: "Qo'ng'iroq qilingan",
}

JIYUN_ORDER_STATUS: dict[int, str] = {
    1: "Kutilmoqda",
    2: "To'lov kutilmoqda",
    3: "Jo'natishga tayyorlanmoqda",
    4: "Jo'natilgan",
    5: "Qabul qilingan",
}

DAIGOU_ORDER_STATUS: dict[int, str] = {
    0: "To'lov kutilmoqda",
    1: "To'langan",
    2: "Sotib olinmoqda",
    3: "Sotib olingan",
    4: "Sklatda kutilmoqda",
    5: "Sklatda",
    6: "Yo'lda",
    10: "Bekor qilingan",
    11: "O'chirilgan",
    12: "Muammoli buyurtma",
}

# ── Rus ────────────────────────────────────────────────────────────────────
DELIVERY_STATUS_RU: dict[int, str] = {
    1: "В Китае",
    2: "В Казахстане",
    3: "В Узбекистане",
    4: "На центральной станции (ожидает получения)",
    5: "В постомате",
    6: "Почта/курьер",
    7: "Завершён",
    8: "У курьера",
}

DASHBOARD_STATUS_RU: dict[int, str] = {
    1: "Находится в филиале",
    8: "Не позвонили",
    9: "Позвонили",
}

JIYUN_ORDER_STATUS_RU: dict[int, str] = {
    1: "Ожидается",
    2: "Ожидает оплаты",
    3: "Готовится к отправке",
    4: "Отправлен",
    5: "Принято",
}

DAIGOU_ORDER_STATUS_RU: dict[int, str] = {
    0: "Ожидает оплаты",
    1: "Оплачено",
    2: "Покупается",
    3: "Куплено",
    4: "Ожидает на складе",
    5: "На складе",
    6: "В пути",
    10: "Отменён",
    11: "Удалён",
    12: "Проблемный заказ",
}

# ── Ingliz ─────────────────────────────────────────────────────────────────
DELIVERY_STATUS_EN: dict[int, str] = {
    1: "In China",
    2: "In Kazakhstan",
    3: "In Uzbekistan",
    4: "At central station (awaiting pickup)",
    5: "In postmat",
    6: "Post/courier",
    7: "Completed",
    8: "With courier",
}

JIYUN_ORDER_STATUS_EN: dict[int, str] = {
    1: "Pending",
    2: "Awaiting payment",
    3: "Preparing for shipment",
    4: "Shipped",
    5: "Received",
}

DAIGOU_ORDER_STATUS_EN: dict[int, str] = {
    0: "Awaiting payment",
    1: "Paid",
    2: "Being purchased",
    3: "Purchased",
    4: "Awaiting at warehouse",
    5: "At warehouse",
    6: "In transit",
    10: "Cancelled",
    11: "Deleted",
    12: "Problematic order",
}

# ── Xitoy tili ────────────────────────────────────────────────────────────
DELIVERY_STATUS_ZH: dict[int, str] = {
    1: "在中国",
    2: "在哈萨克斯坦",
    3: "在乌兹别克斯坦",
    4: "在中心站（等待取货）",
    5: "在邮政柜",
    6: "邮政/快递",
    7: "已完成",
    8: "快递员处",
}

JIYUN_ORDER_STATUS_ZH: dict[int, str] = {
    1: "等待中",
    2: "等待付款",
    3: "准备发货",
    4: "已发货",
    5: "已收货",
}

DAIGOU_ORDER_STATUS_ZH: dict[int, str] = {
    0: "等待付款",
    1: "已付款",
    2: "购买中",
    3: "已购买",
    4: "等待入库",
    5: "已入库",
    6: "运输中",
    10: "已取消",
    11: "已删除",
    12: "问题订单",
}

DASHBOARD_STATUS_ZH: dict[int, str] = {
    1: "在取货点",
    8: "未来电",
    9: "已来电",
}

# ── Xitoy CJK status nomlari ───────────────────────────────────────────────
_CJK_STATUS_NAME: dict[str, dict[str, str]] = {
    "已发货": {"uz": "Jo'natilgan", "ru": "Отправлен", "en": "Shipped"},
    "待付款": {"uz": "To'lov kutilmoqda", "ru": "Ожидает оплаты", "en": "Awaiting payment"},
    "待发货": {"uz": "Jo'natish kutilmoqda", "ru": "Ожидает отправки", "en": "Awaiting shipment"},
    "已签收": {"uz": "Qabul qilingan", "ru": "Принято", "en": "Received"},
    "运输中": {"uz": "Yo'lda", "ru": "В пути", "en": "In transit"},
}


def _unknown(lang: str) -> str:
    if lang == "ru":
        return "Неизвестный статус"
    if lang == "en":
        return "Unknown status"
    if lang == "zh":
        return "未知状态"
    return "Noma'lum holat"


def delivery_label(status: int | None, lang: str = "uz_lat") -> str:
    if status is None:
        return _unknown(lang)
    if lang == "ru":
        return DELIVERY_STATUS_RU.get(status, f"Неизвестный статус (код {status})")
    if lang == "en":
        return DELIVERY_STATUS_EN.get(status, f"Unknown status (code {status})")
    if lang == "zh":
        return DELIVERY_STATUS_ZH.get(status, f"未知状态（代码 {status}）")
    return DELIVERY_STATUS.get(status, f"Noma'lum holat (kod {status})")


def jiyun_label(status: int | None, lang: str = "uz_lat") -> str:
    if status is None:
        return _unknown(lang)
    if lang == "ru":
        return JIYUN_ORDER_STATUS_RU.get(status, f"Неизвестный статус (код {status})")
    if lang == "en":
        return JIYUN_ORDER_STATUS_EN.get(status, f"Unknown status (code {status})")
    if lang == "zh":
        return JIYUN_ORDER_STATUS_ZH.get(status, f"未知状态（代码 {status}）")
    return JIYUN_ORDER_STATUS.get(status, f"Noma'lum holat (kod {status})")


def dashboard_label(status: int | None, lang: str = "uz_lat") -> str:
    if status is None:
        return _unknown(lang)
    if status in (2, 3, 4, 5, 6, 7):
        if lang == "ru":
            return "Доставлено"
        if lang == "en":
            return "Delivered"
        if lang == "zh":
            return "已送达"
        return "Yetkazib berilgan"
    if lang == "ru":
        return DASHBOARD_STATUS_RU.get(status, f"Неизвестный статус (код {status})")
    if lang == "en":
        return f"At branch (code {status})"
    if lang == "zh":
        return DASHBOARD_STATUS_ZH.get(status, f"未知状态（代码 {status}）")
    return DASHBOARD_STATUS.get(status, f"Noma'lum holat (kod {status})")


def is_unpicked_dashboard(status: int | None) -> bool:
    return status in (1, 8, 9)


def daigou_label(status: int | None, lang: str = "uz_lat") -> str:
    if status is None:
        return _unknown(lang)
    if lang == "ru":
        return DAIGOU_ORDER_STATUS_RU.get(status, f"Неизвестный статус (код {status})")
    if lang == "en":
        return DAIGOU_ORDER_STATUS_EN.get(status, f"Unknown status (code {status})")
    if lang == "zh":
        return DAIGOU_ORDER_STATUS_ZH.get(status, f"未知状态（代码 {status}）")
    return DAIGOU_ORDER_STATUS.get(status, f"Noma'lum holat (kod {status})")


def map_chinese_status_name(name: str, lang: str = "uz_lat") -> str | None:
    """CJK status nomini tilga tarjima qilish."""
    entry = _CJK_STATUS_NAME.get(name.strip())
    if entry is None:
        return None
    if lang == "ru":
        return entry["ru"]
    if lang == "en":
        return entry["en"]
    return entry["uz"]
