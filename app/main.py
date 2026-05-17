from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.exception_handlers import register_exception_handlers
from app.api.middleware import RequestLoggingMiddleware
from app.api.routes import api_router
from app.core.config import get_settings
from app.core.database import dispose_engine
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings)
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
        description=(
            "Pluggable AI layer for customer support. "
            "Classify → FAQ (RAG) | API tool call | operator ticket."
        ),
    )
    application.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(application)
    application.include_router(api_router)
    return application


app = create_app()
