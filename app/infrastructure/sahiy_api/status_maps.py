"""Human-readable labels for Sahiy order status codes (RAG context)."""

from __future__ import annotations

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

# Daigou — Xitoy omborigacha (analytics/daigou)
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


def delivery_label(status: int | None) -> str:
    if status is None:
        return "Noma'lum holat"
    return DELIVERY_STATUS.get(status, f"Noma'lum holat (kod {status})")


def jiyun_label(status: int | None) -> str:
    if status is None:
        return "Noma'lum holat"
    return JIYUN_ORDER_STATUS.get(status, f"Noma'lum holat (kod {status})")


def dashboard_label(status: int | None) -> str:
    if status is None:
        return "Noma'lum holat"
    if status in (2, 3, 4, 5, 6, 7):
        return "Yetkazib berilgan"
    return DASHBOARD_STATUS.get(status, f"Noma'lum holat (kod {status})")


def is_unpicked_dashboard(status: int | None) -> bool:
    return status in (1, 8, 9)


def daigou_label(status: int | None) -> str:
    if status is None:
        return "Noma'lum holat"
    return DAIGOU_ORDER_STATUS.get(status, f"Noma'lum holat (kod {status})")
