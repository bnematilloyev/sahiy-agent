from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.domain.dto import ChatContext
from app.domain.verified_phone import (
    PHONE_MESSAGE_PREFIX,
    SAHIY_USER_MESSAGE_PREFIX,
    sahiy_user_id_from_context,
    verified_phone_from_context,
)
from app.domain.entities import Message


def _msg(content: str) -> Message:
    return Message(
        id=uuid4(),
        session_id=uuid4(),
        role="user",
        content=content,
        msg_type=None,
        created_at=datetime.now(timezone.utc),
    )


def test_phone_from_metadata():
    ctx = ChatContext(
        session_id=uuid4(),
        user_id="1",
        text="qayerda",
        channel="telegram",
        metadata={"verified_phone": "+998 90 111 22 33"},
    )
    assert verified_phone_from_context(ctx) == "998901112233"


def test_sahiy_user_id_from_metadata_and_message():
    ctx = ChatContext(
        session_id=uuid4(),
        user_id="1",
        text="qayerda",
        channel="telegram",
        metadata={"sahiy_user_id": 7991625},
    )
    assert sahiy_user_id_from_context(ctx) == 7991625

    ctx2 = ChatContext(
        session_id=uuid4(),
        user_id="1",
        text="qayerda",
        channel="telegram",
        recent_messages=[_msg(f"{SAHIY_USER_MESSAGE_PREFIX}7991625")],
    )
    assert sahiy_user_id_from_context(ctx2) == 7991625


def test_phone_from_recent_message():
    ctx = ChatContext(
        session_id=uuid4(),
        user_id="1",
        text="qayerda",
        channel="telegram",
        recent_messages=[_msg(f"{PHONE_MESSAGE_PREFIX}998901112233")],
    )
    assert verified_phone_from_context(ctx) == "998901112233"
