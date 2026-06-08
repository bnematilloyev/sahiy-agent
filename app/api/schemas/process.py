from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProcessRequest(BaseModel):
    session_id: UUID
    user_id: str = Field(..., min_length=1, max_length=255)
    text: str = Field(..., min_length=1)
    context: Dict[str, Any] = Field(default_factory=dict)


class ProcessResponse(BaseModel):
    type: str = Field(..., description="auto | api | ticket | error")
    text: str
    ticket_id: Optional[UUID] = None

    # --- extended fields for Go orchestrator ---
    # Backwards-compatible: old Go versions that ignore these fields are safe.

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="RAG/LLM confidence score (0..1). Low values hint that the AI is uncertain.",
    )
    escalate: bool = Field(
        default=False,
        description="True when the AI cannot handle the message and a human operator must take over.",
    )
    handoff_reason: Optional[str] = Field(
        default=None,
        description=(
            "Why escalation is needed. "
            "One of: operator_request | low_confidence | concrete_incident | off_topic | ai_error"
        ),
    )
