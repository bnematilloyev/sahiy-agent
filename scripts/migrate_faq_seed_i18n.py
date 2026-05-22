#!/usr/bin/env python3
"""
faq_100.py va faq_quick_replies.py → ko'p tilli shakl.

Avtomatik: question_uz, answer_uz, question_cyr, answer_cyr (lotindan).
ru / en / zh — qo'lda to'ldirasiz (bo'sh qoldiriladi).

Ishlatish:
  python scripts/migrate_faq_seed_i18n.py
"""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.uz_cyrillic import ensure_uz_lat_and_cyr

ROOT = Path(__file__).resolve().parents[1]
FAQ_100_PATH = ROOT / "scripts" / "data" / "faq_100.py"
QUICK_PATH = ROOT / "scripts" / "data" / "faq_quick_replies.py"

_I18N_OPTIONAL = (
    "question_ru",
    "answer_ru",
    "question_en",
    "answer_en",
    "question_zh",
    "answer_zh",
)


def _load_list(path: Path, var_name: str) -> list[dict[str, Any]]:
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var_name:
                    return ast.literal_eval(node.value)
    raise ValueError(f"{var_name} not found in {path}")


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _format_entry(item: dict[str, Any]) -> str:
    lines = ["    {"]
    order = [
        "id",
        "category",
        "question_uz",
        "answer_uz",
        "question_cyr",
        "answer_cyr",
        *_I18N_OPTIONAL,
        "source_type",
        "source_id",
    ]
    for key in order:
        if key not in item or item[key] is None:
            continue
        val = item[key]
        if isinstance(val, str) and "\n" in val:
            lines.append(f'        "{key}": (')
            for part in val.split("\n"):
                lines.append(f'            "{_escape(part)}"')
            lines.append("        ),")
        elif isinstance(val, str):
            lines.append(f'        "{key}": "{_escape(val)}",')
        else:
            lines.append(f'        "{key}": {json.dumps(val, ensure_ascii=False)},')
    lines.append("    }")
    return "\n".join(lines)


def _migrate_item(
    raw: dict[str, Any],
    *,
    keep_manual_langs: bool = False,
) -> dict[str, Any]:
    if raw.get("question_uz"):
        q_uz = str(raw["question_uz"]).strip()
        a_uz = str(raw.get("answer_uz") or "").strip()
    else:
        q_uz = str(raw.get("question") or "").strip()
        a_uz = str(raw.get("answer") or "").strip()

    q_uz, a_uz, q_cyr, a_cyr = ensure_uz_lat_and_cyr(q_uz, a_uz)
    if raw.get("question_cyr"):
        q_cyr = str(raw["question_cyr"]).strip()
    if raw.get("answer_cyr"):
        a_cyr = str(raw["answer_cyr"]).strip()

    out: dict[str, Any] = {
        "id": int(raw["id"]),
        "category": str(raw.get("category") or "general"),
        "question_uz": q_uz,
        "answer_uz": a_uz,
        "question_cyr": q_cyr,
        "answer_cyr": a_cyr,
    }
    if keep_manual_langs:
        for key in _I18N_OPTIONAL:
            val = raw.get(key)
            if val and str(val).strip():
                out[key] = str(val).strip()
    if raw.get("source_type") is not None:
        out["source_type"] = raw["source_type"]
    if raw.get("source_id") is not None:
        out["source_id"] = raw["source_id"]
    return out


def _write(path: Path, var_name: str, doc: str, entries: list[dict[str, Any]]) -> None:
    body = ",\n".join(_format_entry(e) for e in entries)
    path.write_text(f"{doc}\n\n{var_name} = [\n{body}\n]\n", encoding="utf-8")
    print(f"Wrote {path} ({len(entries)} entries)")


_MANUAL_LANG_IDS = frozenset({1, 2})


def _load_git_faq_100() -> list[dict[str, Any]]:
    src = subprocess.check_output(
        ["git", "show", "HEAD:scripts/data/faq_100.py"],
        text=True,
        cwd=ROOT,
    )
    module = ast.parse(src)
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "FAQ_ENTRIES":
                    return ast.literal_eval(node.value)
    raise ValueError("FAQ_ENTRIES not in git HEAD")


def main() -> None:
    # faq_100: git (lotin) + faqat 1–2-id qo'lda tarjima (agar faylda bo'lsa)
    git_faq = _load_git_faq_100()
    # Qo'lda tarjima namunalari (id 1–2) — fayl buzilgan bo'lsa ham ishlaydi
    _MANUAL_BY_ID: dict[int, dict[str, str]] = {
        1: {
            "question_uz": "Buyurtma qachon yetib keladi?",
            "answer_uz": (
                "To'lov tasdiqlangandan so'ng sotuvchidan omborga yetkazish odatda 3–7 ish kuni oladi. "
                "Xitoydan O'zbekistonga yetkazish esa 12–20 kun (ba'zan chegara yoki bayramlarda 25 kungacha). "
                "Jami taxminan 15–25 kun ichida yetkazilishi kutiladi."
            ),
            "question_cyr": "Буюртма қачон етиб келади?",
            "answer_cyr": (
                "Тўлов тасдиқлангандан сўнг сотувчидан омборга етказиш одатда 3–7 иш куни олади. "
                "Хитойдан Ўзбекистонга етказиш эса 12–20 кун (баъзан чегара ёки байрамларда 25 кунгача). "
                "Жами тахминан 15–25 кун ичида етказилиши кутилади."
            ),
            "question_ru": "Когда прибудет заказ?",
            "answer_ru": (
                "После подтверждения оплаты доставка от продавца на склад обычно занимает 3–7 рабочих дней. "
                "Доставка из Китая в Узбекистан — 12–20 дней (иногда до 25 дней из-за границы или праздников). "
                "В общей сложности ожидается 15–25 дней."
            ),
            "question_en": "When will the order arrive?",
            "answer_en": (
                "After payment confirmation, delivery from seller to warehouse usually takes 3–7 business days. "
                "Delivery from China to Uzbekistan takes 12–20 days (sometimes up to 25 days due to borders or holidays). "
                "Total expected time is 15–25 days."
            ),
            "question_zh": "订单什么时候到？",
            "answer_zh": "付款确认后，从卖家到仓库通常需要3-7个工作日。从中国到乌兹别克斯坦需12-20天（有时因边境或节日最多25天）。总计预计15-25天。",
        },
        2: {
            "question_uz": 'Nega buyurtmam hali "Yo\'lda" yoki "Jo\'natish kutilmoqda" holatida turibdi?',
            "answer_uz": (
                "Bu odatiy holat. Sotuvchi tovarni omborga yetkazgandan keyin holat yangilanadi. "
                "Bayram kunlarida yoki chegara yuklamalarida kechikish bo'lishi mumkin. "
                "Buyurtma raqamini yuborsangiz aniq holatni tekshirib beramiz."
            ),
            "question_cyr": 'Нега буюртмам ҳали "Йўлда" ёки "Жўнатиш кутилмоқда" ҳолатида турибди?',
            "answer_cyr": (
                "Бу одатий ҳолат. Сотувчи товарни омборга етказгандан кейин ҳолат янгиланади. "
                "Байрам кунларида ёки чегара юкламаларида кечикиш бўлиши мумкин. "
                "Буюртма рақамини юборсангиз аниқ ҳолатни текшириб берамиз."
            ),
            "question_ru": 'Почему мой заказ всё ещё в статусе "В пути" или "Ожидается отправка"?',
            "answer_ru": (
                "Это обычная ситуация. Статус обновится после того, как продавец доставит товар на склад. "
                "Задержки возможны в праздничные дни или при загруженности границы. "
                "Отправьте номер заказа, мы проверим точный статус."
            ),
            "question_en": 'Why is my order still in "On the way" or "Awaiting shipment" status?',
            "answer_en": (
                "This is a normal situation. The status will update after the seller delivers the goods to the warehouse. "
                "Delays may occur during holidays or border congestion. "
                "Send your order number and we will check the exact status."
            ),
            "question_zh": "为什么我的订单还在“在途”或“等待发货”状态？",
            "answer_zh": "这是正常情况。卖家将货物送到仓库后状态会更新。节假日或边境繁忙时可能延迟。请发送订单号，我们会检查确切状态。",
        },
    }

    faq = []
    for raw in git_faq:
        keep = raw["id"] in _MANUAL_LANG_IDS
        merged = dict(raw)
        if keep:
            merged.update(_MANUAL_BY_ID[raw["id"]])
        faq.append(_migrate_item(merged, keep_manual_langs=keep))

    git_quick_src = subprocess.check_output(
        ["git", "show", "HEAD:scripts/data/faq_quick_replies.py"],
        text=True,
        cwd=ROOT,
    )
    quick_module = ast.parse(git_quick_src)
    git_quick: list[dict[str, Any]] = []
    for node in quick_module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "QUICK_REPLY_FAQ_ENTRIES":
                    git_quick = ast.literal_eval(node.value)
    quick = [_migrate_item(x) for x in git_quick]

    _write(
        FAQ_100_PATH,
        "FAQ_ENTRIES",
        '"""Sahiy FAQ — uz (lotin) + kirill. ru/en/zh qo\'lda to\'ldiring."""',
        faq,
    )
    _write(
        QUICK_PATH,
        "QUICK_REPLY_FAQ_ENTRIES",
        '"""Quick replies FAQ — uz (lotin) + kirill. ru/en/zh qo\'lda to\'ldiring."""',
        quick,
    )


if __name__ == "__main__":
    main()
