from __future__ import annotations

from app.core.prompts import SAHIY_COMPANY_ANSWER


def test_sahiy_company_answer_has_delivery_and_catalog():
    assert "12" in SAHIY_COMPANY_ANSWER
    assert "20 kun" in SAHIY_COMPANY_ANSWER
    assert "million" in SAHIY_COMPANY_ANSWER.lower()
    assert "Xitoy" in SAHIY_COMPANY_ANSWER
    assert "_______" in SAHIY_COMPANY_ANSWER
