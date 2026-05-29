from fastapi import APIRouter

from app.core.config import get_settings
from app.models import ConfigTemplateResponse

router = APIRouter(prefix="/api/v1", tags=["config"])


@router.get("/config/default", response_model=ConfigTemplateResponse)
async def get_default_config() -> ConfigTemplateResponse:
    settings = get_settings()
    return ConfigTemplateResponse(
        server={
            "host": settings.server_host,
            "port": settings.server_port,
            "max_upload_size_mb": settings.max_upload_size_mb,
            "max_concurrent_jobs": settings.max_concurrent_jobs,
        },
        translation={
            "provider": settings.translator_provider,
            "model": settings.translator_model,
            "base_url": settings.translator_base_url,
            "default_target_lang": settings.default_target_lang,
            "mode": settings.translation_mode,
            "math_mode": settings.math_mode,
        },
        ocr={
            "provider": settings.ocr_provider,
            "enabled": settings.ocr_enabled,
        },
        render={
            "mode": settings.render_mode,
            "pdf_compress_dpi": settings.pdf_compress_dpi,
        },
        pipeline={
            "default_source_lang": settings.default_source_lang,
            "preserve_layout": True,
            "output_formats": ["pdf", "markdown", "zip", "all"],
        },
    )
