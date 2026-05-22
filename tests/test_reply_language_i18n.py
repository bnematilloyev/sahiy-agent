from app.domain.reply_language import EN, RU, ZH, detect_reply_language, resolve_reply_language


def test_detect_english():
    assert detect_reply_language("Where is my order?") == EN


def test_detect_chinese():
    assert detect_reply_language("我的订单在哪里？") == ZH


def test_detect_russian():
    assert detect_reply_language("Где мой заказ?") == RU


def test_resolve_keeps_en_in_meta():
    assert resolve_reply_language("ok", {"reply_language": EN}, None) == EN
