"""Adapter to invoke original RetainPDF Python pipeline entrypoints."""

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _get_retain_root() -> Path:
    return get_settings().retain_pdf_root.resolve()


def _ensure_retain_in_path() -> None:
    root = _get_retain_root()
    scripts = root / "backend" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))


def _build_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    settings = get_settings()
    if settings.translator_api_key:
        env["DEEPSEEK_API_KEY"] = settings.translator_api_key
    if settings.ocr_api_key:
        env["MINERU_API_KEY"] = settings.ocr_api_key
    if extra:
        env.update(extra)
    return env


def _run_subprocess(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env_extra: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    logger.info("Running subprocess: %s", " ".join(cmd))
    env = _build_env(env_extra)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        logger.info("Subprocess return code: %d", result.returncode)
        if result.stdout:
            logger.debug("stdout:\n%s", result.stdout[-2000:])
        if result.stderr:
            logger.debug("stderr:\n%s", result.stderr[-2000:])
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired as e:
        logger.error("Subprocess timed out after %s seconds", timeout)
        return {
            "returncode": -1,
            "stdout": e.stdout or "",
            "stderr": e.stderr or "",
            "timeout": True,
        }
    except Exception as e:
        logger.exception("Subprocess failed")
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
        }


# ---------------------------------------------------------------------------
# Full pipeline via retain-pdf provider entrypoint (spec-driven)
# ---------------------------------------------------------------------------

def _build_provider_spec(
    job_id: str,
    job_root: Path,
    source_pdf: Path,
    provider: str,
    ocr_api_key: Optional[str],
    translator_api_key: Optional[str],
    base_url: Optional[str],
    model: Optional[str],
    mode: str,
    math_mode: str,
    render_mode: str,
) -> Dict[str, Any]:
    """Build a provider.stage.v1 spec JSON for run_provider_case.py."""
    return {
        "schema_version": "provider.stage.v1",
        "stage": "provider",
        "job": {
            "job_id": job_id,
            "job_root": str(job_root.resolve()),
            "workflow": "translate",
        },
        "source": {
            "file_url": "",
            "file_path": str(source_pdf.resolve()),
        },
        "ocr": {
            "provider": provider,
            "credential_ref": "env:MINERU_API_KEY" if ocr_api_key else "",
            "model_version": "vlm",
            "paddle_api_url": "",
            "paddle_model": "PaddleOCR-VL-1.5",
            "is_ocr": False,
            "disable_formula": False,
            "disable_table": False,
            "language": "ch",
            "page_ranges": "",
            "data_id": "",
            "no_cache": False,
            "cache_tolerance": 900,
            "extra_formats": "",
            "poll_interval": 5,
            "poll_timeout": 1800,
        },
        "translation": {
            "start_page": 0,
            "end_page": -1,
            "batch_size": 1,
            "workers": 100,
            "mode": mode,
            "math_mode": math_mode,
            "skip_title_translation": False,
            "classify_batch_size": 12,
            "rule_profile_name": "general_sci",
            "custom_rules_text": "",
            "glossary_id": "",
            "glossary_name": "",
            "glossary_resource_entry_count": 0,
            "glossary_inline_entry_count": 0,
            "glossary_overridden_entry_count": 0,
            "glossary_entries": [],
            "context_mode": "needed",
            "glossary_mode": "matched",
            "memory_mode": "matched",
            "model": model or "deepseek-v4-flash",
            "base_url": base_url or "https://api.deepseek.com/v1",
            "credential_ref": "env:DEEPSEEK_API_KEY" if translator_api_key else "",
        },
        "render": {
            "render_mode": render_mode,
            "compile_workers": 0,
            "typst_font_family": "",
            "pdf_compress_dpi": 150,
            "translated_pdf_name": "",
            "body_font_size_factor": 1.0,
            "body_leading_factor": 1.0,
            "inner_bbox_shrink_x": 0.0,
            "inner_bbox_shrink_y": 0.0,
            "inner_bbox_dense_shrink_x": 0.0,
            "inner_bbox_dense_shrink_y": 0.0,
            "font_unify_mode": "role_min",
            "source_cleanup_strategy": "pikepdf_text_strip",
        },
    }


def run_ocr(
    source_pdf: Path,
    output_dir: Path,
    provider: Optional[str] = None,
    job_id: str = "",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    mode: Optional[str] = None,
    math_mode: Optional[str] = None,
    render_mode: Optional[str] = None,
    ocr_api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full provider-backed pipeline (OCR + translate + render).

    Since retain-pdf's run_provider_ocr.py is now spec-driven and executes
    the complete workflow, we generate a provider.stage.v1 spec JSON and
    invoke it. The function name remains "run_ocr" for backward compat
    with task_worker, but it actually runs the full pipeline.
    """
    root = _get_retain_root()
    scripts = root / "backend" / "scripts"
    output_dir.mkdir(parents=True, exist_ok=True)

    provider = (provider or get_settings().ocr_provider).strip().lower()
    entry = scripts / "entrypoints" / "run_provider_ocr.py"

    if not entry.exists():
        # Direct import fallback (legacy path)
        try:
            _ensure_retain_in_path()
            from runtime.pipeline.ocr_normalize import normalize_pdf
        except ModuleNotFoundError as e:
            retain_root = _get_retain_root()
            return {
                "success": False,
                "normalized_json": None,
                "stderr": (
                    f"RetainPDF source not found at {retain_root}. "
                    f"Please clone https://github.com/wxyhgk/retain-pdf to {retain_root} "
                    f"or set RETAIN_PDF_ROOT env var. Original error: {e}"
                ),
            }
        result = normalize_pdf(str(source_pdf), str(output_dir))
        return {"success": True, "normalized_json": output_dir / "document.json", "result": result}

    # Pre-create job directory structure expected by retain-pdf's job_dirs_from_explicit_args
    for subdir in ("source", "ocr", "translated", "rendered", "artifacts", "logs"):
        (output_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Build spec JSON
    settings = get_settings()
    spec = _build_provider_spec(
        job_id=job_id or "local",
        job_root=output_dir,
        source_pdf=source_pdf,
        provider=provider,
        ocr_api_key=ocr_api_key or settings.ocr_api_key,
        translator_api_key=api_key or settings.translator_api_key,
        base_url=base_url or settings.translator_base_url,
        model=model or settings.translator_model,
        mode=mode or settings.translation_mode,
        math_mode=math_mode or settings.math_mode,
        render_mode=render_mode or settings.render_mode,
    )

    spec_path = output_dir / "pipeline.spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    cmd = [
        sys.executable,
        str(entry),
        "--spec",
        str(spec_path.resolve()),
    ]

    env_extra = {}
    effective_ocr_key = ocr_api_key or settings.ocr_api_key
    effective_trans_key = api_key or settings.translator_api_key
    if effective_ocr_key:
        env_extra["MINERU_API_KEY"] = effective_ocr_key
    if effective_trans_key:
        env_extra["DEEPSEEK_API_KEY"] = effective_trans_key

    res = _run_subprocess(cmd, cwd=scripts, env_extra=env_extra, timeout=3600)
    success = res["returncode"] == 0

    # Heuristic: find the generated normalized JSON and output PDF
    normalized_json = None
    output_pdf = None
    if success:
        # Look in the standard retain-pdf job directory structure
        rendered_dir = output_dir / "rendered"
        if rendered_dir.exists():
            pdf_candidates = list(rendered_dir.glob("*.pdf"))
            if pdf_candidates:
                output_pdf = sorted(pdf_candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]

        ocr_dir = output_dir / "ocr"
        if ocr_dir.exists():
            json_candidates = list(ocr_dir.rglob("*.json"))
            for c in sorted(json_candidates, key=lambda p: p.stat().st_mtime, reverse=True):
                if "document" in c.name.lower():
                    normalized_json = c
                    break

    return {
        "success": success,
        "normalized_json": normalized_json,
        "output_pdf": output_pdf,
        "stdout": res["stdout"],
        "stderr": res["stderr"],
    }


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

def run_translation(
    source_json: Path,
    source_pdf: Path,
    output_dir: Path,
    output_pdf: Path,
    job_id: str,
    target_lang: str = "zh",
    source_lang: Optional[str] = None,
    mode: Optional[str] = None,
    math_mode: Optional[str] = None,
    render_mode: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    workers: int = 100,
    batch_size: int = 1,
) -> Dict[str, Any]:
    """Run the full document flow (translation + rendering)."""
    root = _get_retain_root()
    scripts = root / "backend" / "scripts"
    entry = scripts / "entrypoints" / "run_document_flow.py"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    settings = get_settings()

    if entry.exists():
        cmd = [
            sys.executable,
            str(entry),
            "--source-json",
            str(source_json),
            "--source-pdf",
            str(source_pdf),
            "--output-dir",
            str(output_dir.relative_to(output_dir.anchor)) if output_dir.is_absolute() else str(output_dir),
            "--output",
            str(output_pdf.name),
            "--mode",
            mode or settings.translation_mode,
            "--math-mode",
            math_mode or settings.math_mode,
            "--render-mode",
            render_mode or settings.render_mode,
            "--workers",
            str(workers),
            "--batch-size",
            str(batch_size),
            "--job-id",
            job_id,
            "--output-root",
            str(settings.output_dir.resolve()),
        ]
        if api_key:
            cmd.extend(["--api-key", api_key])
        if base_url:
            cmd.extend(["--base-url", base_url])
        if model:
            cmd.extend(["--model", model])
        if source_lang:
            cmd.extend(["--source-lang", source_lang])  # if supported

        env_extra = {}
        if api_key:
            env_extra["DEEPSEEK_API_KEY"] = api_key

        res = _run_subprocess(cmd, cwd=scripts, env_extra=env_extra, timeout=3600)
        success = res["returncode"] == 0
        return {
            "success": success,
            "stdout": res["stdout"],
            "stderr": res["stderr"],
            "output_pdf": output_pdf if output_pdf.exists() else None,
        }
    else:
        # Direct import fallback
        try:
            _ensure_retain_in_path()
            from runtime.pipeline.book_pipeline import run_book_pipeline
        except ModuleNotFoundError as e:
            retain_root = _get_retain_root()
            return {
                "success": False,
                "stderr": (
                    f"RetainPDF source not found at {retain_root}. "
                    f"Please clone https://github.com/wxyhgk/retain-pdf to {retain_root} "
                    f"or set RETAIN_PDF_ROOT env var. Original error: {e}"
                ),
            }
        result = run_book_pipeline(
            source_json_path=source_json,
            source_pdf_path=source_pdf,
            output_dir=output_dir,
            output_pdf_path=output_pdf,
            api_key=api_key or settings.translator_api_key,
            model=model or settings.translator_model,
            base_url=base_url or settings.translator_base_url,
            mode=mode or settings.translation_mode,
            math_mode=math_mode or settings.math_mode,
            render_mode=render_mode or settings.render_mode,
        )
        return {"success": True, "result": result, "output_pdf": output_pdf}


# ---------------------------------------------------------------------------
# Markdown export (if supported by original project)
# ---------------------------------------------------------------------------

def export_markdown(
    job_output_dir: Path,
    dest: Path,
) -> Path:
    """Try to export markdown from job outputs."""
    # Heuristic: look for .md files or create from JSON
    md_candidates = list(job_output_dir.rglob("*.md"))
    if md_candidates:
        shutil.copy2(md_candidates[0], dest)
        return dest
    # Fallback: return empty md
    dest.write_text("# Markdown export not available for this job\n", encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# Bundle / ZIP
# ---------------------------------------------------------------------------

def create_zip_bundle(
    job_output_dir: Path,
    dest_zip: Path,
) -> Path:
    """Create a ZIP containing all job outputs."""
    import zipfile

    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    dest_zip_resolved = dest_zip.resolve()
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in job_output_dir.rglob("*"):
            if f.is_file() and f.resolve() != dest_zip_resolved:
                arcname = f.relative_to(job_output_dir).as_posix()
                zf.write(f, arcname)
    return dest_zip
