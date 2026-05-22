"""Unit tests for admin daigou response parsing (no live API)."""

from app.infrastructure.sahiy_api.admin_auth import _extract_token, _is_success
from app.infrastructure.sahiy_api.daigou_admin import (
    _extract_items,
    _extract_single,
    _money,
    _parse_order,
    parse_detail_from_row,
)


def test_is_success_ret_codes():
    assert _is_success({"ret": 1, "data": {}})
    assert _is_success({"ret": 200, "data": {}})
    assert not _is_success({"ret": 0, "msg": "fail"})


def test_extract_token_shapes():
    assert _extract_token({"ret": 1, "data": {"access_token": "eyJabc"}}) == "eyJabc"
    assert _extract_token({"ret": 1, "data": "eyJdirect"}) == "eyJdirect"
    assert _extract_token({"ret": 0, "data": {"access_token": "x"}}) is None


def test_extract_single_from_list():
    body = [{"id": 99, "order_sn": "DG1", "skus": []}]
    assert _extract_single(body)["order_sn"] == "DG1"


def test_extract_items_nested():
    body = {"data": {"data": [{"id": 1, "order_sn": "DG2", "skus": []}]}}
    items = _extract_items(body)
    assert len(items) == 1
    assert items[0]["order_sn"] == "DG2"


def test_money_fen_to_yuan():
    assert _money(2250) == 22.5
    assert _money(22.5) == 22.5
    assert _money(0) == 0.0


def test_parse_order_with_skus():
    row = {
        "id": 1,
        "order_sn": "DG60492966",
        "status": 6,
        "amount": 5000,
        "skus": [
            {
                "name": "Test product",
                "quantity": 2,
                "price": 1500,
                "amount": 3000,
                "sku_info": {"sku_img": "https://img.example/a.jpg", "specs": [{"label": "Color", "value": "Red"}]},
            }
        ],
    }
    detail = _parse_order(row)
    assert detail is not None
    assert detail.order_sn == "DG60492966"
    assert len(detail.skus) == 1
    assert detail.skus[0].price == 15.0
    assert detail.skus[0].amount == 30.0
    assert detail.skus[0].images == ["https://img.example/a.jpg"]
    assert detail.skus[0].spec_label == "Color: Red"


def test_parse_detail_from_row_requires_skus():
    assert parse_detail_from_row({"id": 1, "order_sn": "DG1"}) is None
    assert parse_detail_from_row({"id": 1, "order_sn": "DG1", "skus": [{"name": "x", "quantity": 1}]})
