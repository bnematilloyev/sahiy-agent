from __future__ import annotations

from app.domain.product_search_present import format_product_caption, product_buy_keyboard_extra
from app.infrastructure.sahiy_api.product_search import (
    ProductSearchItem,
    build_goods_deeplink,
    parse_search_response,
    reply_language_to_api_header,
)


def test_parse_search_response_sample():
    body = {
        "ret": 1,
        "data": {
            "items": {
                "item": [
                    {
                        "detail_url": "https://detail.1688.com/offer/906661447054.html",
                        "title": "test mahsulot",
                        "pic_url": "https://example.com/p.jpg",
                        "price": "50.63",
                        "direct_price": "33.75",
                        "cargo_fee": "16.88",
                        "sales": 490,
                        "num_iid": 906661447054,
                    }
                ]
            }
        },
    }
    items = parse_search_response(body)
    assert len(items) == 1
    assert items[0].title == "test mahsulot"
    assert items[0].price_cny == 50.63


def test_build_goods_deeplink():
    url = "https://detail.1688.com/offer/919430791153.html"
    link = build_goods_deeplink(url)
    assert link.startswith("https://sahiy.uz/GoodsDetailView?u=")
    assert "919430791153" in link
    assert "detail.1688.com" in link


def test_reply_language_header():
    assert reply_language_to_api_header("ru") == "ru_RU"
    assert reply_language_to_api_header("en") == "en_US"


def test_product_buy_keyboard_has_url():
    item = ProductSearchItem(
        title="A",
        pic_url="https://x.com/a.jpg",
        detail_url="https://detail.1688.com/offer/1.html",
        price_cny=10,
        direct_price_cny=8,
        cargo_fee_cny=2,
        sales=1,
    )
    extra = product_buy_keyboard_extra(item, "uz_lat")
    btn = extra["inline_keyboard"][0][0]
    assert btn["text"] == "🛒 Sotib olish"
    assert "GoodsDetailView" in btn["url"]


def test_format_product_caption_uzs():
    item = ProductSearchItem(
        title="Kiyim",
        pic_url="https://x.com/a.jpg",
        detail_url="https://detail.1688.com/offer/1.html",
        price_cny=10.0,
        direct_price_cny=8.0,
        cargo_fee_cny=2.0,
        sales=100,
    )
    text = format_product_caption(item, "uz_lat", cny_to_uzs=1750, index=1)
    assert "Kiyim" in text
    assert "so'm" in text
    assert "Sotuvlar" in text
