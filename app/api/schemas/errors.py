from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str = Field(..., examples=["service_unavailable"])
    message: str
    request_id: Optional[str] = None
