"""Pydantic settings for RetainPDF Server."""

import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    server_host: str = Field(default="0.0.0.0", alias="SERVER_HOST")
    server_port: int = Field(default=8000, alias="SERVER_PORT")

    # Paths
    upload_dir: Path = Field(default=Path("./data/uploads"), alias="UPLOAD_DIR")
    output_dir: Path = Field(default=Path("./data/outputs"), alias="OUTPUT_DIR")
    temp_dir: Path = Field(default=Path("./data/temp"), alias="TEMP_DIR")
    job_db: Path = Field(default=Path("./data/jobs.db"), alias="JOB_DB")

    # RetainPDF source (where the original project lives)
    retain_pdf_root: Path = Field(
        default=Path("./retain-pdf"), alias="RETAIN_PDF_ROOT"
    )

    # Translation
    translator_provider: Literal["deepseek", "openai", "custom"] = Field(
        default="deepseek", alias="TRANSLATOR_PROVIDER"
    )
    translator_api_key: Optional[str] = Field(default=None, alias="TRANSLATOR_API_KEY")
    translator_base_url: Optional[str] = Field(
        default="https://api.deepseek.com/v1", alias="TRANSLATOR_BASE_URL"
    )
    translator_model: str = Field(default="deepseek-chat", alias="TRANSLATOR_MODEL")

    # OCR
    ocr_provider: Literal["mineru", "paddle", "custom"] = Field(
        default="mineru", alias="OCR_PROVIDER"
    )
    ocr_api_key: Optional[str] = Field(default=None, alias="OCR_API_KEY")
    ocr_enabled: bool = Field(default=True, alias="OCR_ENABLED")

    # Pipeline tuning
    max_upload_size_mb: int = Field(default=200, alias="MAX_UPLOAD_SIZE_MB")
    max_concurrent_jobs: int = Field(default=2, alias="MAX_CONCURRENT_JOBS")
    translation_mode: Literal["fast", "precise", "sci"] = Field(
        default="sci", alias="TRANSLATION_MODE"
    )
    math_mode: Literal["placeholder", "direct_typst"] = Field(
        default="direct_typst", alias="MATH_MODE"
    )
    render_mode: Literal["auto", "overlay", "typst", "dual"] = Field(
        default="typst", alias="RENDER_MODE"
    )
    pdf_compress_dpi: int = Field(default=150, alias="PDF_COMPRESS_DPI")
    default_target_lang: str = Field(default="zh", alias="DEFAULT_TARGET_LANG")
    default_source_lang: Optional[str] = Field(default=None, alias="DEFAULT_SOURCE_LANG")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_dir: Path = Field(default=Path("./data/logs"), alias="LOG_DIR")

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


def get_settings() -> Settings:
    return Settings()
