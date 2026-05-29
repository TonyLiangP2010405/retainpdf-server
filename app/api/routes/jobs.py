"""Job API routes: create, status, download, delete."""

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.models import (
    ConfigTemplateResponse,
    DeleteJobResponse,
    DownloadResponse,
    ErrorCode,
    ErrorResponse,
    JobCreatedResponse,
    JobListResponse,
    JobStatus,
    JobStatusResponse,
    OutputFormat,
    Stage,
)
from app.services.job_service import (
    create_job,
    delete_job as delete_job_db,
    get_job,
    list_jobs,
    update_job,
)
from app.workers.task_worker import cancel_job as cancel_worker_job, get_active_count, start_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["jobs"])


def _job_to_response(job: Dict[str, Any]) -> JobStatusResponse:
    error = job.get("error")
    output_paths = job.get("output_paths")
    return JobStatusResponse(
        job_id=job["job_id"],
        status=JobStatus(job.get("status", "queued")),
        progress=job.get("progress", 0),
        stage=Stage(job["stage"]) if job.get("stage") else None,
        created_at=job["created_at"],
        updated_at=job["updated_at"],
        source_lang=job.get("source_lang"),
        target_lang=job.get("target_lang", "zh"),
        output_format=OutputFormat(job.get("output_format", "pdf")),
        error=error,
        output_paths=output_paths,
    )


@router.post("/jobs", response_model=JobCreatedResponse)
async def create_job_endpoint(
    file: UploadFile = File(..., description="PDF file to translate"),
    source_lang: Optional[str] = Form(None),
    target_lang: str = Form("zh"),
    translator: Optional[str] = Form(None),
    ocr_enabled: bool = Form(True),
    preserve_layout: bool = Form(True),
    output_format: str = Form("pdf"),
    config: Optional[str] = Form(None),
) -> JobCreatedResponse:
    settings = get_settings()

    # Validate file
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error={"code": ErrorCode.INVALID_FILE.value, "message": "Only PDF files are supported"}
            ).model_dump(),
        )

    # Size check
    contents = await file.read()
    if len(contents) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error={
                    "code": ErrorCode.FILE_TOO_LARGE.value,
                    "message": f"File exceeds {settings.max_upload_size_mb} MB limit",
                }
            ).model_dump(),
        )

    # Save upload
    upload_dir = settings.upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name.replace("/", "_").replace("\\", "_")
    upload_path = upload_dir / safe_name
    upload_path.write_bytes(contents)
    logger.info("Uploaded %s (%d bytes) to %s", safe_name, len(contents), upload_path)

    # Parse config JSON string
    config_dict: Optional[Dict[str, Any]] = None
    if config:
        import json
        try:
            config_dict = json.loads(config)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error={"code": ErrorCode.INVALID_FILE.value, "message": "Invalid config JSON"}
                ).model_dump(),
            )

    # Concurrency check
    if get_active_count() >= settings.max_concurrent_jobs:
        # Still accept but will queue
        pass

    job_id = create_job(
        source_lang=source_lang,
        target_lang=target_lang,
        translator=translator,
        ocr_enabled=ocr_enabled,
        preserve_layout=preserve_layout,
        output_format=output_format,
        config=config_dict,
        upload_path=str(upload_path),
    )
    logger.info("Created job %s for file %s", job_id, safe_name)

    # Start background worker
    start_job(job_id)

    return JobCreatedResponse(job_id=job_id, status="queued", message="job created")


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs_endpoint(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> JobListResponse:
    rows = list_jobs(limit=limit, offset=offset)
    return JobListResponse(
        jobs=[_job_to_response(r) for r in rows],
        total=len(rows),
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error={"code": ErrorCode.JOB_NOT_FOUND.value, "message": f"Job {job_id} not found"}
            ).model_dump(),
        )
    return _job_to_response(job)


@router.delete("/jobs/{job_id}", response_model=DeleteJobResponse)
async def delete_job_endpoint(job_id: str) -> DeleteJobResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error={"code": ErrorCode.JOB_NOT_FOUND.value, "message": f"Job {job_id} not found"}
            ).model_dump(),
        )

    # Cancel if running
    cancel_worker_job(job_id)

    # Delete DB record
    deleted = delete_job_db(job_id)

    # Delete files
    try:
        settings = get_settings()
        upload_path = Path(job.get("upload_path", ""))
        if upload_path.exists():
            upload_path.unlink()
        job_dir = settings.output_dir / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir)
    except Exception as exc:
        logger.exception("Failed to delete job files for %s", job_id)

    return DeleteJobResponse(
        job_id=job_id,
        deleted=deleted,
        message="Job and associated files deleted" if deleted else "Job not found",
    )


@router.get("/jobs/{job_id}/download")
async def download_result(
    job_id: str,
    format: str = Query("pdf", description="pdf | markdown | zip | all"),
) -> FileResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error={"code": ErrorCode.JOB_NOT_FOUND.value, "message": f"Job {job_id} not found"}
            ).model_dump(),
        )

    if job.get("status") != JobStatus.SUCCEEDED.value:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error={
                    "code": ErrorCode.PIPELINE_ERROR.value,
                    "message": f"Job not ready (status: {job.get('status')})",
                }
            ).model_dump(),
        )

    output_paths = job.get("output_paths", {})
    settings = get_settings()
    job_dir = settings.output_dir / job_id

    file_path: Optional[Path] = None
    media_type = "application/octet-stream"
    filename = f"{job_id}"

    fmt = format.lower()
    if fmt == "pdf":
        file_path = Path(output_paths.get("pdf", "")) if output_paths else None
        if not file_path or not file_path.exists():
            # fallback search
            candidates = list(job_dir.rglob("*-translated.pdf")) + list(job_dir.rglob("*.pdf"))
            if candidates:
                file_path = candidates[0]
        media_type = "application/pdf"
        filename = f"{job_id}.pdf"
    elif fmt == "markdown":
        file_path = Path(output_paths.get("markdown", "")) if output_paths else None
        if not file_path or not file_path.exists():
            candidates = list(job_dir.rglob("*.md"))
            if candidates:
                file_path = candidates[0]
        media_type = "text/markdown"
        filename = f"{job_id}.md"
    elif fmt == "zip" or fmt == "all":
        file_path = Path(output_paths.get("zip", "")) if output_paths else None
        if not file_path or not file_path.exists():
            zip_path = job_dir / "bundle.zip"
            if zip_path.exists():
                file_path = zip_path
        media_type = "application/zip"
        filename = f"{job_id}.zip"
    else:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error={"code": ErrorCode.INVALID_FILE.value, "message": f"Unknown format: {format}"}
            ).model_dump(),
        )

    if not file_path or not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error={
                    "code": ErrorCode.PIPELINE_ERROR.value,
                    "message": f"Output file not found for format '{format}'",
                }
            ).model_dump(),
        )

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
    )
