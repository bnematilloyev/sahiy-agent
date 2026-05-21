from __future__ import annotations

import pytest

from app.core.prompts import CLASSIFIER_SYSTEM, CLASSIFIER_USER_TEMPLATE, wrap_user_message
from app.domain.enums import QuestionCategory
from app.infrastructure.llm.rules_ai import RulesAi

pytestmark = pytest.mark.asyncio


@pytest.fixture
def rules_ai() -> RulesAi:
    return RulesAi()


def _classifier_prompt(text: str) -> str:
    return CLASSIFIER_USER_TEMPLATE.format(wrapped=wrap_user_message(text))


async def test_detects_faq(rules_ai: RulesAi):
    result = await rules_ai.complete(
        CLASSIFIER_SYSTEM,
        _classifier_prompt("Yetkazib berish qancha vaqt oladi?"),
    )
    assert result == QuestionCategory.FAQ.value


async def test_detects_order(rules_ai: RulesAi):
    result = await rules_ai.complete(
        CLASSIFIER_SYSTEM,
        _classifier_prompt("Buyurtmam DG123 qayerda?"),
    )
    assert result == QuestionCategory.API.value


async def test_detects_support(rules_ai: RulesAi):
    result = await rules_ai.complete(
        CLASSIFIER_SYSTEM,
        _classifier_prompt("Kecha tovar singan keldi, foto yuboraman"),
    )
    assert result == QuestionCategory.TICKET.value


async def test_hypothetical_return_is_faq(rules_ai: RulesAi):
    result = await rules_ai.complete(
        CLASSIFIER_SYSTEM,
        _classifier_prompt("Buyurtma singan kelsa qaytarib olasizlarmi?"),
    )
    assert result == QuestionCategory.FAQ.value
