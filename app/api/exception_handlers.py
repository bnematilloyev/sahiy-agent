from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.schemas.errors import ErrorResponse
from app.core.http import request_id_from
from app.core.exceptions import (
    ConfigurationError,
    DatabaseError,
    LLMError,
    LLMTimeoutError,
    SahiyAgentError,
    SessionAccessDeniedError,
    SessionClosedError,
    SessionNotFoundError,
)
from app.core.prompts import BUSY_MESSAGE

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(LLMTimeoutError)
    async def llm_timeout_handler(request: Request, exc: LLMTimeoutError) -> JSONResponse:
        rid = request_id_from(request)
        logger.warning("LLM timeout request_id=%s: %s", rid, exc)
        body = ErrorResponse(error="llm_timeout", message=BUSY_MESSAGE, request_id=rid)
        return JSONResponse(status_code=503, content=body.model_dump())

    @app.exception_handler(LLMError)
    async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
        rid = request_id_from(request)
        logger.warning("LLM error request_id=%s: %s", rid, exc)
        body = ErrorResponse(error="llm_error", message=BUSY_MESSAGE, request_id=rid)
        return JSONResponse(status_code=503, content=body.model_dump())

    @app.exception_handler(ConfigurationError)
    async def config_error_handler(request: Request, exc: ConfigurationError) -> JSONResponse:
        rid = request_id_from(request)
        body = ErrorResponse(error="configuration_error", message=str(exc), request_id=rid)
        return JSONResponse(status_code=503, content=body.model_dump())

    @app.exception_handler(SessionNotFoundError)
    async def session_not_found_handler(
        request: Request, exc: SessionNotFoundError
    ) -> JSONResponse:
        rid = request_id_from(request)
        body = ErrorResponse(error="session_not_found", message=str(exc), request_id=rid)
        return JSONResponse(status_code=404, content=body.model_dump())

    @app.exception_handler(SessionAccessDeniedError)
    async def session_access_handler(
        request: Request, exc: SessionAccessDeniedError
    ) -> JSONResponse:
        rid = request_id_from(request)
        body = ErrorResponse(error="session_access_denied", message=str(exc), request_id=rid)
        return JSONResponse(status_code=403, content=body.model_dump())

    @app.exception_handler(SessionClosedError)
    async def session_closed_handler(request: Request, exc: SessionClosedError) -> JSONResponse:
        rid = request_id_from(request)
        body = ErrorResponse(error="session_closed", message=str(exc), request_id=rid)
        return JSONResponse(status_code=409, content=body.model_dump())

    @app.exception_handler(DatabaseError)
    async def database_error_handler(request: Request, exc: DatabaseError) -> JSONResponse:
        rid = request_id_from(request)
        logger.exception("Database error request_id=%s", rid)
        body = ErrorResponse(
            error="database_error",
            message="Ma'lumotlar bazasi vaqtincha ishlamayapti.",
            request_id=rid,
        )
        return JSONResponse(status_code=503, content=body.model_dump())

    @app.exception_handler(SahiyAgentError)
    async def sahiy_error_handler(request: Request, exc: SahiyAgentError) -> JSONResponse:
        rid = request_id_from(request)
        body = ErrorResponse(error="agent_error", message=str(exc), request_id=rid)
        return JSONResponse(status_code=500, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = request_id_from(request)
        body = ErrorResponse(
            error="validation_error",
            message="So'rov formati noto'g'ri.",
            request_id=rid,
        )
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        rid = request_id_from(request)
        body = ErrorResponse(
            error="http_error",
            message=str(exc.detail),
            request_id=rid,
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        rid = request_id_from(request)
        logger.exception("Unhandled error request_id=%s", rid)
        body = ErrorResponse(
            error="internal_error",
            message="Kutilmagan xatolik yuz berdi.",
            request_id=rid,
        )
        return JSONResponse(status_code=500, content=body.model_dump())
