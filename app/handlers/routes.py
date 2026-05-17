from __future__ import annotations

import logging
from typing import Dict

from app.domain.enums import QuestionCategory
from app.handlers.base import IntentHandler

logger = logging.getLogger(__name__)


class IntentRouter:
    """Pick the right handler for faq / api / ticket."""

    def __init__(self, handlers: Dict[QuestionCategory, IntentHandler]) -> None:
        self._handlers = handlers

    def pick(self, category: QuestionCategory) -> IntentHandler:
        handler = self._handlers.get(category)
        if handler is None:
            logger.warning("No handler for %s, using FAQ", category)
            handler = self._handlers.get(QuestionCategory.FAQ)
        if handler is None:
            raise KeyError("FAQ handler is not registered")
        return handler
