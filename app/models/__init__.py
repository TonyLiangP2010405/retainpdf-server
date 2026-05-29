"""Pydantic request/response models for the API."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OutputFormat(str, Enum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    ZIP = "zip"
    ALL = "all"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Stage(str, Enum):
    UPLOAD = "upload"
    OCR = "ocr"
    TRANSLATE = "translate"
    LAYOUT = "layout"
    RENDER = "render"
    DONE = "done"


class ErrorCode(str, Enum):
    INVALID_FILE = "INVALID_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    PIPELINE_ERROR = "PIPELINE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    CONFIG_ERROR = "CONFIG_ERROR"


# ---------- Requests ----------

class CreateJobRequest(BaseModel):
    source_lang: Optional[str] = Field(None, description="Source language code")
    target_lang: str = Field("zh", description="Target language code")
    translator: Optional[str] = Field(None, description="Translator provider override")
    ocr_enabled: bool = Field(True, description="Enable OCR for scanned/image PDFs")
    preserve_layout: bool = Field(True, description="Preserve original layout")
    output_format: OutputFormat = Field(OutputFormat.PDF, description="Desired output format")
    config: Optional[Dict[str, Any]] = Field(None, description="Advanced config JSON")


class ConfigTemplateRequest(BaseModel):
    pass


# ---------- Responses ----------

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    service: str = "retain-pdf-server"


class JobCreatedResponse(BaseModel):
    job_id: str
    status: str = "queued"
    message: str = "job created"


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int = Field(0, ge=0, le=100)
    stage: Optional[Stage] = None
    created_at: datetime
    updated_at: datetime
    source_lang: Optional[str] = None
    target_lang: str = "zh"
    output_format: OutputFormat = OutputFormat.PDF
    error: Optional[Dict[str, Any]] = None
    output_paths: Optional[Dict[str, str]] = None


class JobListResponse(BaseModel):
    jobs: List[JobStatusResponse]
    total: int


class DownloadResponse(BaseModel):
    job_id: str
    format: OutputFormat
    download_url: str


class ErrorResponse(BaseModel):
    error: Dict[str, Any]


class ConfigTemplateResponse(BaseModel):
    server: Dict[str, Any]
    translation: Dict[str, Any]
    ocr: Dict[str, Any]
    render: Dict[str, Any]
    pipeline: Dict[str, Any]


class DeleteJobResponse(BaseModel):
    job_id: str
    deleted: bool
    message: str
