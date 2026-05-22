"""Unit tests for custom-daigou-orders parsing and track matching."""

from app.infrastructure.sahiy_api.custom_daigou import (
    _row_matches_track,
    extract_custom_daigou_page,
)
from app.infrastructure.sahiy_api.daigou_admin import parse_detail_from_row


SAMPLE_PAGE = {
    "data": [
        {
            "id": 665233,
            "user_id": 7991625,
            "order_sn": "DG60492965",
            "amount": 5.12,
            "goods_amount": 1.62,
            "status": 6,
            "status_name": "交易完成",
            "expresses": [
                {
                    "pivot": {"express_num": "435147294520990"},
                }
            ],
            "purchase_packages": [
                {"express_num": "435147294520990"},
            ],
            "skus": [
                {
                    "name": "frisbee product",
                    "platform": "1688",
                    "platform_url": "https://detail.1688.com/offer/716610732946.html",
                    "platform_sku": "6044882172216",
                    "price": 1.62,
                    "actual_price": 0,
                    "quantity": 1,
                    "amount": 1.62,
                    "sku_info": {
                        "specs": [
                            {
                                "label": "spetsifikatsiyalar",
                                "value": "20cmtpr oq uchish disk",
                            }
                        ],
                        "sku_img": "https://cbu01.alicdn.com/img/example.jpg",
                    },
                }
            ],
        }
    ],
    "meta": {"current_page": 1, "last_page": 3, "total": 25},
    "ret": 1,
}


def test_extract_custom_daigou_page():
    items, current, last, total = extract_custom_daigou_page(SAMPLE_PAGE)
    assert len(items) == 1
    assert current == 1
    assert last == 3
    assert total == 25


def test_row_matches_track_express_num():
    row = SAMPLE_PAGE["data"][0]
    assert _row_matches_track(row, "435147294520990")
    assert _row_matches_track(row, "DG60492965")
    assert not _row_matches_track(row, "999999999999999")


def test_parse_custom_daigou_row_actual_price_fallback():
    detail = parse_detail_from_row(SAMPLE_PAGE["data"][0])
    assert detail is not None
    assert detail.order_sn == "DG60492965"
    assert len(detail.skus) == 1
    sku = detail.skus[0]
    assert sku.actual_price == 1.62
    assert sku.price == 1.62
    assert sku.images == ["https://cbu01.alicdn.com/img/example.jpg"]
