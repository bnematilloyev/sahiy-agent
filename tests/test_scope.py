from __future__ import annotations

from app.domain.scope import is_off_topic, is_operator_request


def test_football_is_off_topic():
    assert is_off_topic("Barsa bilan Real oxirgi marta nechchi o'ynadi?")


def test_delivery_is_not_off_topic():
    assert not is_off_topic("Buyurtmam qachon yetib keladi?")


def test_operator_request_is_not_off_topic_flag():
    assert is_operator_request("Operatorga ulab bering")
    assert not is_off_topic("Operatorga ulab bering")


def test_personal_chat_is_off_topic():
    assert is_off_topic("Operator yaxshi ko'rgan qizi bormi?")
