"""Telegram mahsulot qidiruv natijalari — rasm, narx, sotib olish deeplink."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.domain.order_present import format_uzs
from app.domain.reply_language import EN, RU, UZ_CYRL, UZ_LAT, ZH
from app.infrastructure.sahiy_api.product_search import (
    ProductSearchItem,
    build_goods_deeplink,
)

_BUY: Dict[str, str] = {
    UZ_LAT: "🛒 Sotib olish",
    UZ_CYRL: "🛒 Сотиб олиш",
    RU: "🛒 Купить",
    EN: "🛒 Buy",
    ZH: "🛒 购买",
}

_PRICE: Dict[str, str] = {
    UZ_LAT: "Narx",
    UZ_CYRL: "Нарх",
    RU: "Цена",
    EN: "Price",
    ZH: "价格",
}

_DIRECT: Dict[str, str] = {
    UZ_LAT: "Chegirmali",
    UZ_CYRL: "Чегирмали",
    RU: "Со скидкой",
    EN: "Discounted",
    ZH: "优惠价",
}

_CARGO: Dict[str, str] = {
    UZ_LAT: "Yetkazish (Xitoy)",
    UZ_CYRL: "Етказиш (Хитой)",
    RU: "Доставка (Китай)",
    EN: "Delivery (China)",
    ZH: "配送（中国）",
}

_SALES: Dict[str, str] = {
    UZ_LAT: "Sotuvlar",
    UZ_CYRL: "Сотувлар",
    RU: "Продажи",
    EN: "Sales",
    ZH: "销量",
}


def _t(table: Dict[str, str], lang: str) -> str:
    return table.get(lang) or table.get(UZ_LAT, "")


def format_product_caption(
    item: ProductSearchItem,
    lang: str,
    *,
    cny_to_uzs: float,
    index: int,
) -> str:
    title = item.title
    if len(title) > 200:
        title = title[:197].rstrip() + "…"
    lines = [f"{index}. {title}", ""]
    if item.price_cny > 0:
        lines.append(f"{_t(_PRICE, lang)}: {format_uzs(item.price_cny, cny_to_uzs, lang)}")
    if item.direct_price_cny > 0 and abs(item.direct_price_cny - item.price_cny) > 0.01:
        lines.append(
            f"{_t(_DIRECT, lang)}: {format_uzs(item.direct_price_cny, cny_to_uzs, lang)}"
        )
    if item.cargo_fee_cny > 0:
        lines.append(
            f"{_t(_CARGO, lang)}: {format_uzs(item.cargo_fee_cny, cny_to_uzs, lang)}"
        )
    if item.sales > 0:
        lines.append(f"{_t(_SALES, lang)}: {item.sales:,}".replace(",", " "))
    return "\n".join(lines)


def product_buy_keyboard_extra(item: ProductSearchItem, lang: str) -> Dict[str, Any]:
    deeplink = build_goods_deeplink(item.detail_url)
    return {
        "inline_keyboard": [
            [{"text": _t(_BUY, lang), "url": deeplink}],
        ]
    }
