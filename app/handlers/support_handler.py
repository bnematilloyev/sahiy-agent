from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.core.prompts import (
    BROKEN_ITEM_ACK,
    HANDOFF_OFF_TOPIC,
    HANDOFF_OPERATOR_REQUEST,
    HANDOFF_UNRESOLVED,
    OPEN_TICKET_OFF_TOPIC,
    OPEN_TICKET_REMINDER,
    TICKET_ACK_EMPATHETIC,
    TICKET_ACK_TEMPLATE,
)
from app.domain.classification import is_concrete_incident
from app.domain.dto import HANDOFF_REASON_KEY, ChatContext, ChatReply
from app.domain.enums import QuestionCategory, ResponseType, TicketStatus
from app.domain.keywords import infer_ticket_type
from app.domain.text_normalize import normalize_text as _normalize_text
from app.domain.scope import is_off_topic, is_operator_request
from app.repositories.ticket_repository import TicketRepository

if TYPE_CHECKING:
    from app.handlers.faq_handler import FaqHandler


class SupportHandler:
    category = QuestionCategory.TICKET

    def __init__(self, tickets: TicketRepository) -> None:
        self._tickets = tickets
        self._faq: Optional[FaqHandler] = None

    def bind_faq(self, faq_handler: FaqHandler) -> None:
        self._faq = faq_handler

    async def reply(self, context: ChatContext) -> ChatReply:
        reason = str(context.metadata.get(HANDOFF_REASON_KEY, "")).strip()
        open_ticket = await self._tickets.get_open_for_session(context.session_id)

        if open_ticket:
            if reason in ("off_topic", "unresolved", "operator_request") or is_operator_request(
                context.text
            ):
                text = (
                    OPEN_TICKET_OFF_TOPIC.format(ticket_id=open_ticket.id)
                    if reason == "off_topic" or is_off_topic(context.text)
                    else OPEN_TICKET_REMINDER.format(ticket_id=open_ticket.id)
                )
                return ChatReply(
                    response_type=ResponseType.TICKET,
                    text=text,
                    category=self.category,
                    ticket_id=open_ticket.id,
                )
            if self._faq and _is_policy_question(context.text):
                return await self._faq.reply(context)
            return ChatReply(
                response_type=ResponseType.TICKET,
                text=OPEN_TICKET_REMINDER.format(ticket_id=open_ticket.id),
                category=self.category,
                ticket_id=open_ticket.id,
            )

        if not is_concrete_incident(context.text) and reason not in (
            "off_topic",
            "operator_request",
        ):
            if self._faq:
                return await self._faq.reply(context)

        ticket_type = self._resolve_ticket_type(context, reason)
        ticket = await self._tickets.create(
            session_id=context.session_id,
            user_id=context.user_id,
            ticket_type=ticket_type,
            status=TicketStatus.OPEN.value,
        )
        ack = self._ack_message(ticket.id, ticket_type, reason)
        return ChatReply(
            response_type=ResponseType.TICKET,
            text=ack,
            category=self.category,
            ticket_id=ticket.id,
        )

    @staticmethod
    def _resolve_ticket_type(context: ChatContext, reason: str) -> str:
        if reason == "off_topic":
            return "off_topic"
        if reason == "unresolved":
            return "unresolved"
        if is_operator_request(context.text):
            return "operator_request"
        return infer_ticket_type(context.text)

    @staticmethod
    def _ack_message(ticket_id, ticket_type: str, reason: str) -> str:
        if reason == "off_topic" or ticket_type == "off_topic":
            return HANDOFF_OFF_TOPIC.format(ticket_id=ticket_id)
        if reason == "unresolved" or ticket_type == "unresolved":
            return HANDOFF_UNRESOLVED.format(ticket_id=ticket_id)
        if ticket_type == "operator_request":
            return HANDOFF_OPERATOR_REQUEST.format(ticket_id=ticket_id)
        if ticket_type == "broken":
            return BROKEN_ITEM_ACK.format(ticket_id=ticket_id)
        if ticket_type == "delivery":
            return TICKET_ACK_EMPATHETIC.format(ticket_id=ticket_id)
        return TICKET_ACK_TEMPLATE.format(ticket_id=ticket_id)


def _is_policy_question(text: str) -> bool:
    """FAQ-style questions should be answered even when a ticket is already open."""
    if is_operator_request(text):
        return False
    lowered = _normalize_text(text)
    if "?" not in text and len(lowered) > 100:
        return False
    hints = (
        "qaytar",
        "singan",
        "brak",
        "buzil",
        "kompaniya",
        "sahiy",
        "mumkinmi",
        "qanday",
        "qancha",
        "yetkaz",
        "to'lov",
        "kafolat",
        "ishlayapsiz",
        "javob",
    )
    return any(hint in lowered for hint in hints)
