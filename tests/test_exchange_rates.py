"""Tests for CNY→UZS exchange rate and SKU price formatting."""

import pytest

from app.domain.order_present import (
    _localize_spec_label,
    format_sku_text,
    format_uzs,
)
from app.infrastructure.sahiy_api.daigou_admin import DaigouOrderDetail, SkuInfo
from app.infrastructure.sahiy_api.exchange_rates import parse_cny_uzs_rate


def test_parse_cny_uzs_rate():
    body = {
        "ret": 1,
        "data": [
            {"from": "CNY", "currency_code": "USD", "rate": "0.1500"},
            {"from": "CNY", "currency_code": "UZS", "rate": "1750.0000"},
        ],
    }
    assert parse_cny_uzs_rate(body) == 1750.0


def test_format_uzs():
    assert format_uzs(7.26, 1750, "uz_lat") == "12 705 so'm"
    assert format_uzs(9.26, 1750, "ru") == "16 205 сум"


def test_localize_spec_label():
    assert _localize_spec_label("尺码", "uz_lat") == "O'lcham"
    assert _localize_spec_label("颜色分类", "ru") == "Цвет"
    assert _localize_spec_label("颜色", "en") == "Color"


def test_format_sku_text_in_uzs():
    detail = DaigouOrderDetail(
        order_id=1,
        order_sn="DG1",
        status=6,
        status_name="",
        goods_amount=7.26,
        amount=9.26,
        freight_fee=2.0,
        skus=[
            SkuInfo(
                name="Test slipper",
                platform="1688",
                platform_url="",
                platform_sku="",
                quantity=1,
                price=7.26,
                actual_price=7.26,
                amount=7.26,
                specs=[
                    {"label": "尺码", "value": "44-45"},
                    {"label": "颜色分类", "value": "228 qora"},
                ],
            )
        ],
    )
    text = format_sku_text(detail, "uz_lat", cny_to_uzs=1750)
    assert "Mahsulot:" in text
    assert "_______" not in text
    assert "O'lcham: 44-45" in text
    assert "Rang: 228 qora" in text
    assert "Miqdor: 1 dona" in text
    assert "Yetkazish: 3 500 so'm" in text
    assert "16 205 so'm" in text
    assert "Jami" in text or "jami" in text
    assert "Do'kon: 1688" in text
    assert "¥" not in text


def test_order_pricing_from_row_freight_fallback():
    from app.infrastructure.sahiy_api.daigou_admin import order_pricing_from_row

    pricing = order_pricing_from_row({"goods_amount": 5062, "amount": 6062})
    assert pricing["goods_amount"] == pytest.approx(50.62)
    assert pricing["amount"] == pytest.approx(60.62)
    assert pricing["freight_fee"] == pytest.approx(10.0)


def test_enrich_order_summary_uzs():
    from app.domain.order_present import enrich_order_summary_uzs

    summary = {
        "bolimlar": {
            "jiyun_orders": {
                "buyurtmalar": [
                    {
                        "sn": "773405557484852",
                        "holat": "Yakunlangan",
                        "narx_cny": {
                            "goods_amount": 50.62,
                            "freight_fee": 10.0,
                            "amount": 60.62,
                        },
                    }
                ]
            }
        }
    }
    out = enrich_order_summary_uzs(summary, 1750, "uz_lat")
    item = out["bolimlar"]["jiyun_orders"]["buyurtmalar"][0]
    assert item["mahsulot_jami"] == "88 585 so'm"
    assert item["xitoy_ichida_yetkazish"] == "17 500 so'm"
    assert item["jami"] == "106 085 so'm"
    assert "narx_cny" not in item


def test_format_sku_text_russian():
    detail = DaigouOrderDetail(
        order_id=1,
        order_sn="DG1",
        status=6,
        status_name="",
        goods_amount=9.26,
        amount=9.26,
        skus=[
            SkuInfo(
                name="Test",
                platform="1688",
                platform_url="",
                platform_sku="",
                quantity=2,
                price=7.26,
                actual_price=7.26,
                amount=14.52,
                specs=[{"label": "颜色", "value": "black"}],
            )
        ],
    )
    text = format_sku_text(detail, "ru", cny_to_uzs=1750, inline=False)
    assert "Товары" in text
    assert "Цвет: black" in text
    assert "Количество: 2 шт" in text
    assert "Итого по заказу:" in text
