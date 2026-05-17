from enum import Enum


class SessionStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class QuestionCategory(str, Enum):
    """Classifier output — which processing path to take."""

    FAQ = "faq"
    API = "api"
    TICKET = "ticket"


class ResponseType(str, Enum):
    """Stored in messages.msg_type and returned as HTTP `type`."""

    AUTO = "auto"
    API = "api"
    TICKET = "ticket"
    ERROR = "error"


# Backward-compatible alias (same values as ResponseType for message rows).
MessageType = ResponseType


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"
