"""Telegram: kategoriya ro'yxati va inline tugmalar."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.domain.reply_language import EN, RU, UZ_CYRL, UZ_LAT, ZH
from app.infrastructure.sahiy_api.categories_1688 import Category1688, category_display_name

CALLBACK_PREFIX = "ct"
MAX_BUTTONS = 12


_HEADER_LIST: Dict[str, str] = {
    UZ_LAT: "📂 Sahiy katalog bo'limlari. Keraklisini tanlang:",
    UZ_CYRL: "📂 Саҳий каталог бўлимлари. Кераклисини танланг:",
    RU: "📂 Разделы каталога Sahiy. Выберите нужный:",
    EN: "📂 Sahiy catalog sections. Pick one:",
    ZH: "📂 Sahiy 商品分类。请选择：",
}

_HEADER_MATCHED: Dict[str, str] = {
    UZ_LAT: "📂 «{query}» bo'yicha mos bo'limlar:",
    UZ_CYRL: "📂 «{query}» бўйича мос бўлимлар:",
    RU: "📂 Подходящие разделы по запросу «{query}»:",
    EN: "📂 Sections matching «{query}»:",
    ZH: "📂 与「{query}」相关的分类：",
}

_HEADER_CHILDREN: Dict[str, str] = {
    UZ_LAT: "📂 {name} — ichki bo'limlar:",
    UZ_CYRL: "📂 {name} — ички бўлимлар:",
    RU: "📂 {name} — подразделы:",
    EN: "📂 {name} — subcategories:",
    ZH: "📂 {name} — 子分类：",
}

_HEADER_SEARCHING: Dict[str, str] = {
    UZ_LAT: "🔍 «{name}» bo'limidagi mahsulotlar qidirilmoqda…",
    UZ_CYRL: "🔍 «{name}» бўлимидаги маҳсулотлар қидирилмоқда…",
    RU: "🔍 Ищем товары в разделе «{name}»…",
    EN: "🔍 Searching products in «{name}»…",
    ZH: "🔍 正在搜索「{name}」分类中的商品…",
}

_BACK: Dict[str, str] = {
    UZ_LAT: "⬅️ Orqaga",
    UZ_CYRL: "⬅️ Орқага",
    RU: "⬅️ Назад",
    EN: "⬅️ Back",
    ZH: "⬅️ 返回",
}

_EMPTY: Dict[str, str] = {
    UZ_LAT: "Bu bo'limda hozircha kategoriya yo'q. Boshqa bo'limni tanlang yoki mahsulot nomini yozing.",
    UZ_CYRL: "Бу бўлимда ҳозирча категория йўқ. Бошқа бўлимни танланг ёки маҳсулот номини ёзинг.",
    RU: "В этом разделе пока нет категорий. Выберите другой раздел или введите название товара.",
    EN: "No subcategories here yet. Pick another section or type a product name.",
    ZH: "此分类下暂无子分类。请选择其他分类或输入商品名称。",
}


def _t(table: Dict[str, str], lang: str) -> str:
    return table.get(lang) or table.get(UZ_LAT, "")


def list_header(lang: str, *, query: str = "", parent_name: str = "") -> str:
    if parent_name:
        return _t(_HEADER_CHILDREN, lang).format(name=parent_name)
    if query.strip():
        return _t(_HEADER_MATCHED, lang).format(query=query.strip()[:80])
    return _t(_HEADER_LIST, lang)


def searching_header(lang: str, category_name: str) -> str:
    return _t(_HEADER_SEARCHING, lang).format(name=category_name[:80])


def empty_children_text(lang: str) -> str:
    return _t(_EMPTY, lang)


def build_category_keyboard(
    categories: Sequence[Category1688],
    lang: str,
    *,
    back_target: int = 0,
    current_list_parent: Optional[int] = None,
) -> List[List[Dict[str, str]]]:
    rows: List[List[Dict[str, str]]] = []
    row: List[Dict[str, str]] = []
    list_parent = current_list_parent if current_list_parent is not None else 0
    for cat in categories[:MAX_BUTTONS]:
        label = category_display_name(cat, lang)[:32]
        row.append(
            {
                "text": label,
                "callback_data": f"{CALLBACK_PREFIX}_o_{cat.id}_{list_parent}",
            }
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if back_target >= 0 and (back_target > 0 or current_list_parent is not None):
        rows.append(
            [{"text": _t(_BACK, lang), "callback_data": f"{CALLBACK_PREFIX}_b_{back_target}"}]
        )
    return rows


def parse_category_callback(data: str) -> Optional[Tuple[str, int, int]]:
    """
    ct_o_{id}_{back} — ochish (back = oldingi ro'yxat parent_id, 0 = root)
    ct_b_{id} — orqaga (0 = root)
    """
    if not data.startswith(f"{CALLBACK_PREFIX}_"):
        return None
    parts = data.split("_")
    if len(parts) < 3:
        return None
    action = parts[1]
    if action == "b" and len(parts) == 3:
        try:
            return action, int(parts[2]), 0
        except ValueError:
            return None
    if action == "o" and len(parts) >= 4:
        try:
            return action, int(parts[2]), int(parts[3])
        except ValueError:
            return None
    return None
