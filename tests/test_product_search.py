from __future__ import annotations

from app.domain.product_search_present import format_product_caption, product_buy_keyboard_extra
from app.domain.product_search_present import product_search_see_all_keyboard
from app.infrastructure.sahiy_api.categories_1688 import parse_categories_response
from app.infrastructure.sahiy_api.product_search import (
    ProductSearchItem,
    build_category_search_deeplink,
    build_goods_deeplink,
    build_product_search_deeplink,
    parse_search_response,
    reply_language_to_api_header,
)
from urllib.parse import parse_qs, urlparse


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


def test_build_product_search_deeplink():
    link = build_product_search_deeplink("kurtka", page_size=20)
    assert link.startswith("https://sahiy.uz/search?")
    qs = parse_qs(urlparse(link).query)
    assert qs["q"] == ["kurtka"]
    assert qs["platform"] == ["1688"]
    assert "PurchaseSearchView" not in link
    assert "keyword=" not in link


def test_build_product_search_deeplink_chinese_query():
    link = build_product_search_deeplink("夏季 帽子")
    qs = parse_qs(urlparse(link).query)
    assert qs["q"] == ["夏季 帽子"]
    assert "platform=1688" in link


def test_build_category_search_deeplink():
    link = build_category_search_deeplink("皮草", "Mo'ynali kiyimlar")
    assert link.startswith("https://sahiy.uz/search?")
    qs = parse_qs(urlparse(link).query)
    assert qs["category"] == ["皮草"]
    assert qs["displayName"] == ["Mo'ynali kiyimlar"]
    assert qs["platform"] == ["1688"]


def test_product_search_see_all_keyboard():
    extra = product_search_see_all_keyboard("lego", "uz_lat", page_size=20)
    btn = extra["inline_keyboard"][0][0]
    assert "Hammasini" in btn["text"]
    assert "q=lego" in btn["url"] or "q=lego" in btn["url"].lower()
    assert "platform=1688" in btn["url"]
    assert "PurchaseSearchView" not in btn["url"]


def test_product_search_see_all_keyboard_category():
    extra = product_search_see_all_keyboard(
        "",
        "uz_lat",
        category="皮草",
        display_name="Mo'ynali kiyimlar",
    )
    btn = extra["inline_keyboard"][0][0]
    assert "category=" in btn["url"]
    assert "displayName=" in btn["url"]
    assert "platform=1688" in btn["url"]
    assert "PurchaseSearchView" not in btn["url"]


def test_parse_categories_response_sample():
    body = {
        "ret": 1,
        "data": [
            {
                "id": 1424,
                "ali_category_id": 19,
                "ali_parent_id": 53,
                "name_uz": "Optik videotasvir",
                "name_ru": "Optika",
                "name_en": "optical",
                "name_cn": "光学",
                "leaf": 0,
                "level": 2,
            }
        ],
    }
    cats = parse_categories_response(body)
    assert len(cats) == 1
    assert cats[0].name_uz == "Optik videotasvir"


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
