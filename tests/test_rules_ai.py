from __future__ import annotations

import pytest

from app.core.prompts import CLASSIFIER_SYSTEM
from app.domain.enums import QuestionCategory
from app.infrastructure.llm.rules_ai import RulesAi

pytestmark = pytest.mark.asyncio


@pytest.fixture
def rules_ai() -> RulesAi:
    return RulesAi()


async def test_detects_faq(rules_ai: RulesAi):
    result = await rules_ai.complete(
        CLASSIFIER_SYSTEM,
        "Xabar: Yetkazib berish qancha vaqt oladi?",
    )
    assert result == QuestionCategory.FAQ.value


async def test_detects_order(rules_ai: RulesAi):
    result = await rules_ai.complete(
        CLASSIFIER_SYSTEM,
        "Xabar: Buyurtmam DG123 qayerda?",
    )
    assert result == QuestionCategory.API.value


async def test_detects_support(rules_ai: RulesAi):
    result = await rules_ai.complete(
        CLASSIFIER_SYSTEM,
        "Xabar: Kecha tovar singan keldi, foto yuboraman",
    )
    assert result == QuestionCategory.TICKET.value


async def test_hypothetical_return_is_faq(rules_ai: RulesAi):
    result = await rules_ai.complete(
        CLASSIFIER_SYSTEM,
        "Xabar: Buyurtma singan kelsa qaytarib olasizlarmi?",
    )
    assert result == QuestionCategory.FAQ.value
