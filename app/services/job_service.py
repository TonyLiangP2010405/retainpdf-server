"""Job persistence and lifecycle management using SQLite."""

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.models import JobStatus, Stage

_lock = threading.Lock()


def _init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path), check_same_thread=False) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'queued',
                stage TEXT,
                progress INTEGER DEFAULT 0,
                source_lang TEXT,
                target_lang TEXT DEFAULT 'zh',
                translator TEXT,
                ocr_enabled INTEGER DEFAULT 1,
                preserve_layout INTEGER DEFAULT 1,
                output_format TEXT DEFAULT 'pdf',
                config_json TEXT,
                error_json TEXT,
                output_paths_json TEXT,
                upload_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"
        )
        conn.commit()


def _ensure_db() -> sqlite3.Connection:
    db_path = get_settings().job_db
    _init_db(db_path)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def create_job(
    source_lang: Optional[str],
    target_lang: str,
    translator: Optional[str],
    ocr_enabled: bool,
    preserve_layout: bool,
    output_format: str,
    config: Optional[Dict[str, Any]],
    upload_path: str,
) -> str:
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        with _ensure_db() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, status, stage, progress,
                    source_lang, target_lang, translator,
                    ocr_enabled, preserve_layout, output_format,
                    config_json, upload_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    JobStatus.QUEUED.value,
                    Stage.UPLOAD.value,
                    0,
                    source_lang,
                    target_lang,
                    translator,
                    1 if ocr_enabled else 0,
                    1 if preserve_layout else 0,
                    output_format,
                    json.dumps(config) if config else None,
                    upload_path,
                    now,
                    now,
                ),
            )
            conn.commit()
    return job_id


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        with _ensure_db() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def list_jobs(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    with _lock:
        with _ensure_db() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_job(
    job_id: str,
    status: Optional[str] = None,
    stage: Optional[str] = None,
    progress: Optional[int] = None,
    error: Optional[Dict[str, Any]] = None,
    output_paths: Optional[Dict[str, str]] = None,
) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    fields: List[str] = ["updated_at = ?"]
    params: List[Any] = [now]

    if status is not None:
        fields.append("status = ?")
        params.append(status)
    if stage is not None:
        fields.append("stage = ?")
        params.append(stage)
    if progress is not None:
        fields.append("progress = ?")
        params.append(progress)
    if error is not None:
        fields.append("error_json = ?")
        params.append(json.dumps(error))
    if output_paths is not None:
        fields.append("output_paths_json = ?")
        params.append(json.dumps(output_paths))

    params.append(job_id)
    sql = f"UPDATE jobs SET {', '.join(fields)} WHERE job_id = ?"
    with _lock:
        with _ensure_db() as conn:
            cur = conn.execute(sql, params)
            conn.commit()
    return cur.rowcount > 0


def delete_job(job_id: str) -> bool:
    with _lock:
        with _ensure_db() as conn:
            cur = conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            conn.commit()
    return cur.rowcount > 0


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d: Dict[str, Any] = {key: row[key] for key in row.keys()}
    for k in ("ocr_enabled", "preserve_layout"):
        if k in d:
            d[k] = bool(d[k])
    for k in ("config_json", "error_json", "output_paths_json"):
        if k in d and d[k] is not None:
            try:
                d[k.replace("_json", "")] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    return d
