from __future__ import annotations

from app.domain.classification import (
    is_company_question,
    is_concrete_incident,
    is_hypothetical_policy_question,
)
from app.domain.keywords import classify_by_keywords


def test_hypothetical_broken_return_is_faq():
    text = "Buyurtma singan kelsa qaytarib olasizlarmi?"
    assert is_hypothetical_policy_question(text)
    assert not is_concrete_incident(text)
    assert classify_by_keywords(text) == "faq"


def test_concrete_broken_is_ticket():
    text = "Kecha buyurtam keldi, singan edi"
    assert is_concrete_incident(text)
    assert classify_by_keywords(text) == "ticket"


def test_company_question_detected():
    assert is_company_question("Sahiy qanday kompaniya?")
    assert is_company_question("Sahiy nima ?")


def test_order_ref_is_api():
    assert classify_by_keywords("Meni DG123456 buyurtmam qayerda") == "api"
