"""Background task worker for executing PDF pipeline jobs."""

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from app.core.config import get_settings
from app.models import JobStatus, Stage
from app.services.job_service import get_job, update_job
from app.services.pipeline_service import create_zip_bundle, export_markdown, run_ocr, run_translation

logger = logging.getLogger(__name__)

_active_jobs: Dict[str, threading.Thread] = {}
_lock = threading.Lock()


def _job_dir(job_id: str) -> Path:
    return get_settings().output_dir / job_id


def start_job(job_id: str) -> None:
    """Spawn a background thread to process a job."""
    with _lock:
        if job_id in _active_jobs:
            logger.warning("Job %s already has an active worker", job_id)
            return
        t = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
        _active_jobs[job_id] = t
        t.start()


def cancel_job(job_id: str) -> bool:
    """Mark a job as cancelled (best-effort)."""
    with _lock:
        thread = _active_jobs.pop(job_id, None)
    if thread:
        # We can't forcefully stop a thread in Python, but we mark it
        update_job(job_id, status=JobStatus.CANCELLED.value, stage=Stage.DONE.value, progress=0)
        return True
    return False


def _run_job(job_id: str) -> None:
    """Main pipeline execution for a single job."""
    job = get_job(job_id)
    if not job:
        logger.error("Job %s not found in DB", job_id)
        return

    settings = get_settings()
    job_dir = _job_dir(job_id)
    upload_path = Path(job["upload_path"])
    output_paths: Dict[str, str] = {}

    # Read per-job config overrides (sent by frontend)
    job_config = job.get("config") or {}
    trans_cfg = job_config.get("translation") or {}
    ocr_cfg = job_config.get("ocr") or {}
    render_cfg = job_config.get("render") or {}

    # Resolve effective settings: job config > env settings
    api_key = trans_cfg.get("api_key") or settings.translator_api_key or None
    base_url = trans_cfg.get("base_url") or settings.translator_base_url or None
    model = trans_cfg.get("model") or settings.translator_model or None
    mode = trans_cfg.get("mode") or settings.translation_mode
    render_mode = render_cfg.get("mode") or settings.render_mode
    ocr_provider = ocr_cfg.get("provider") or settings.ocr_provider
    ocr_api_key = ocr_cfg.get("api_key") or settings.ocr_api_key or None

    try:
        logger.info("[Job %s] Starting pipeline", job_id)
        update_job(job_id, status=JobStatus.RUNNING.value, stage=Stage.OCR.value, progress=5)

        # ------------------------------------------------------------------
        # Stage: Full pipeline (OCR + translate + render via spec-driven entrypoint)
        # ------------------------------------------------------------------
        ocr_dir = job_dir / "ocr"
        ocr_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[Job %s] Running full pipeline...", job_id)

        ocr_result = run_ocr(
            source_pdf=upload_path,
            output_dir=ocr_dir,
            provider=ocr_provider,
            job_id=job_id,
            api_key=api_key,
            base_url=base_url,
            model=model,
            mode=mode,
            math_mode=settings.math_mode,
            render_mode=render_mode,
            ocr_api_key=ocr_api_key,
        )

        if not ocr_result["success"]:
            logger.error("[Job %s] Pipeline failed: %s", job_id, ocr_result.get("stderr", ""))
            stderr_text = str(ocr_result.get("stderr", ""))
            if "No module named" in stderr_text or "RetainPDF source not found" in stderr_text:
                logger.warning("[Job %s] Pipeline skipped because retain-pdf source is unavailable", job_id)
                raise RuntimeError(
                    "RetainPDF source code not found. Please set RETAIN_PDF_ROOT to a valid clone of "
                    "https://github.com/wxyhgk/retain-pdf and ensure all Python dependencies are installed."
                )
            raise RuntimeError(f"Pipeline failed: {stderr_text[:500]}")

        # If the full pipeline produced an output PDF directly, use it
        pipeline_pdf = ocr_result.get("output_pdf")
        if pipeline_pdf and pipeline_pdf.exists():
            logger.info("[Job %s] Full pipeline produced PDF: %s", job_id, pipeline_pdf)
            # Copy/rename to our expected location for download consistency
            final_pdf = job_dir / f"{job_id}-translated.pdf"
            shutil.copy2(pipeline_pdf, final_pdf)
            output_paths["pdf"] = str(final_pdf.resolve())
            update_job(job_id, progress=85, stage=Stage.RENDER.value)
        else:
            # Fallback: try the legacy two-stage path
            logger.warning("[Job %s] Full pipeline did not produce PDF, trying legacy translation...", job_id)
            ocr_json = ocr_result.get("normalized_json")
            source_json = ocr_json or upload_path

            update_job(job_id, stage=Stage.TRANSLATE.value, progress=35)
            trans_dir = job_dir / "translations"
            trans_dir.mkdir(parents=True, exist_ok=True)
            output_pdf = job_dir / f"{job_id}-translated.pdf"

            logger.info("[Job %s] Running translation + render...", job_id)
            trans_result = run_translation(
                source_json=source_json,
                source_pdf=upload_path,
                output_dir=trans_dir,
                output_pdf=output_pdf,
                job_id=job_id,
                target_lang=job.get("target_lang", "zh"),
                source_lang=job.get("source_lang"),
                mode=mode,
                math_mode=settings.math_mode,
                render_mode=render_mode,
                api_key=api_key,
                base_url=base_url,
                model=model,
            )
            if not trans_result["success"]:
                logger.error("[Job %s] Translation failed: %s", job_id, trans_result.get("stderr", ""))
                raise RuntimeError(f"Translation failed: {trans_result.get('stderr', '')}")
            logger.info("[Job %s] Translation complete", job_id)
            update_job(job_id, progress=80, stage=Stage.RENDER.value)

            if output_pdf.exists():
                output_paths["pdf"] = str(output_pdf.resolve())

        # ------------------------------------------------------------------
        # Stage: Post-processing / export
        # ------------------------------------------------------------------
        update_job(job_id, stage=Stage.DONE.value, progress=95)

        # Markdown
        md_path = job_dir / "output.md"
        try:
            # Look for markdown in the retain-pdf output structure
            trans_dir = job_dir / "ocr" / "translated"
            if trans_dir.exists():
                export_markdown(trans_dir, md_path)
                if md_path.exists():
                    output_paths["markdown"] = str(md_path.resolve())
        except Exception:
            logger.exception("[Job %s] Markdown export failed", job_id)

        # ZIP bundle
        zip_path = job_dir / "bundle.zip"
        try:
            create_zip_bundle(job_dir, zip_path)
            output_paths["zip"] = str(zip_path.resolve())
        except Exception:
            logger.exception("[Job %s] ZIP bundle failed", job_id)

        update_job(
            job_id,
            status=JobStatus.SUCCEEDED.value,
            stage=Stage.DONE.value,
            progress=100,
            output_paths=output_paths,
        )
        logger.info("[Job %s] Pipeline succeeded", job_id)

    except Exception as exc:
        logger.exception("[Job %s] Pipeline failed", job_id)
        error_payload = {
            "code": "PIPELINE_ERROR",
            "message": str(exc),
            "type": type(exc).__name__,
        }
        update_job(
            job_id,
            status=JobStatus.FAILED.value,
            stage=Stage.DONE.value,
            error=error_payload,
        )
    finally:
        with _lock:
            _active_jobs.pop(job_id, None)


def get_active_count() -> int:
    with _lock:
        return len(_active_jobs)
