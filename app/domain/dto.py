from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.domain.entities import Message
from app.domain.enums import QuestionCategory, ResponseType


HANDOFF_REASON_KEY = "handoff_reason"


@dataclass(frozen=True)
class ChatContext:
    """One user message plus session state for handlers."""

    session_id: UUID
    user_id: str
    text: str
    channel: str
    recent_messages: List[Message] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def with_handoff_reason(self, reason: str) -> ChatContext:
        meta = {**self.metadata, HANDOFF_REASON_KEY: reason}
        return ChatContext(
            session_id=self.session_id,
            user_id=self.user_id,
            text=self.text,
            channel=self.channel,
            recent_messages=self.recent_messages,
            metadata=meta,
        )


@dataclass(frozen=True)
class ChatReply:
    """Bot reply returned to Telegram, Go, or other clients."""

    response_type: ResponseType
    text: str
    category: QuestionCategory
    ticket_id: Optional[UUID] = None
    channel_extra: Dict[str, Any] = field(default_factory=dict)
