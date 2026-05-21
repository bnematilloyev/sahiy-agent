"""HTTP helpers shared by API middleware and exception handlers."""

from __future__ import annotations

import uuid

from starlette.requests import Request


def request_id_from(request: Request) -> str:
    return request.headers.get("X-Request-ID") or str(uuid.uuid4())
