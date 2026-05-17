from fastapi import APIRouter

from app import __version__
from app.api.schemas.health import HealthResponse
from app.core.config import get_settings
from app.core.database import check_database_connection

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    settings = get_settings()
    db_status = "connected"
    try:
        await check_database_connection()
    except Exception:
        db_status = "disconnected"

    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        app=settings.app_name,
        version=__version__,
        database=db_status,
    )
