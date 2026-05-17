from __future__ import annotations

from typing import Protocol

from app.domain.dto import ChatContext, ChatReply
from app.domain.enums import QuestionCategory


class IntentHandler(Protocol):
    category: QuestionCategory

    async def reply(self, context: ChatContext) -> ChatReply:
        ...
