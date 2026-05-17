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
