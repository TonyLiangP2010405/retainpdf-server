from fastapi import APIRouter

from app.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    from app.core.config import get_settings
    from app import __version__

    return HealthResponse(
        status="ok",
        version=__version__,
        service="retain-pdf-server",
    )
