from __future__ import annotations

import pytest
from telegram.error import BadRequest

from app.channels.telegram.messenger import TelegramMessenger, _is_message_not_modified


def test_is_message_not_modified():
    exc = BadRequest(
        "Message is not modified: specified new message content and reply markup "
        "are exactly the same as a current content and reply markup of the message"
    )
    assert _is_message_not_modified(exc)


@pytest.mark.asyncio
async def test_edit_message_text_treats_not_modified_as_success():
    class FakeMessage:
        def __init__(self) -> None:
            self.edit_calls = 0

        async def edit_text(self, text: str, reply_markup=None) -> None:
            self.edit_calls += 1
            raise BadRequest("Message is not modified: same content")

    messenger = TelegramMessenger(send_retries=3)
    ok = await messenger.edit_message_text(FakeMessage(), "📋 Aktiv buyurtmalar (8 ta)")
    assert ok is True
