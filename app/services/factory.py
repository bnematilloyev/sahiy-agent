"""Wire services for API, Telegram, and tests."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import QuestionCategory
from app.handlers.faq_handler import FaqHandler
from app.handlers.order_handler import OrderHandler
from app.handlers.routes import IntentRouter
from app.handlers.support_handler import SupportHandler
from app.infrastructure.embeddings.factory import create_embedder
from app.infrastructure.llm.factory import create_ai_client
from app.infrastructure.order_api import OrderApi
from app.repositories.faq_repository import FAQRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.session_repository import ChatSessionRepository
from app.repositories.ticket_repository import TicketRepository
from app.services.chat_service import ChatService
from app.services.faq_service import FaqService
from app.services.intent_service import IntentService
from app.services.reply_service import ReplyService


def create_handlers(faq_repo: FAQRepository, ticket_repo: TicketRepository, ai=None) -> IntentRouter:
    ai_client = ai or create_ai_client()
    embedder = create_embedder()
    faq = FaqService(faq_repo, embedder, ai_client)
    support = SupportHandler(ticket_repo)
    faq_handler = FaqHandler(faq, support)
    support.bind_faq(faq_handler)

    return IntentRouter(
        {
            QuestionCategory.FAQ: faq_handler,
            QuestionCategory.API: OrderHandler(OrderApi(get_settings()), ai_client),
            QuestionCategory.TICKET: support,
        }
    )


def create_reply_service(session: AsyncSession) -> ReplyService:
    ai = create_ai_client()
    faq_repo = FAQRepository(session)
    ticket_repo = TicketRepository(session)

    return ReplyService(
        messages=MessageRepository(session),
        intent=IntentService(ai),
        router=create_handlers(faq_repo, ticket_repo, ai),
    )


def create_chat_service(session: AsyncSession) -> ChatService:
    return ChatService(
        sessions=ChatSessionRepository(session),
        replies=create_reply_service(session),
        tickets=TicketRepository(session),
    )
