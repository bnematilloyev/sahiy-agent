from __future__ import annotations

import logging

from app.core.exceptions import LLMError, LLMTimeoutError
from app.core.prompts import CLASSIFIER_SYSTEM, CLASSIFIER_USER_TEMPLATE, wrap_user_message
from app.domain.enums import QuestionCategory
from app.domain.keywords import classify_by_keywords
from app.infrastructure.llm.ports import AiClient

logger = logging.getLogger(__name__)

_VALID = {c.value for c in QuestionCategory}


class IntentService:
    """Detect whether the user needs FAQ, order info, or operator help."""

    def __init__(self, ai: AiClient) -> None:
        self._ai = ai

    async def detect(self, text: str) -> QuestionCategory:
        prompt = CLASSIFIER_USER_TEMPLATE.format(wrapped=wrap_user_message(text))
        try:
            raw = await self._ai.complete(CLASSIFIER_SYSTEM, prompt, max_tokens=16)
        except (LLMTimeoutError, LLMError) as exc:
            logger.warning("Intent LLM failed, using keywords: %s", exc)
            return QuestionCategory(classify_by_keywords(text))

        label = raw.strip().lower().split()[0] if raw.strip() else QuestionCategory.FAQ.value

        if label not in _VALID:
            logger.warning("Unexpected intent '%s', defaulting to faq", raw)
            return QuestionCategory.FAQ
        return QuestionCategory(label)
