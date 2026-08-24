"""SQLite control database for source inventory and resource audit trail."""

import sqlite3
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class ResourceStatus:
    PENDING = "PENDIENTE"
    IN_PROGRESS = "EN_PROCESO"
    PROCESSED = "PROCESADO_EXITOSAMENTE"
    RECOVERED = "RECUPERADO_VIA_CONTINGENCIA"
    DISCONTINUED = "DESCONTINUADO"
    ERROR = "ERROR"


class ControlDatabase:
    """Small dependency-free SQLite audit store."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_inventory (
                source_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                base_url TEXT NOT NULL,
                config_path TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS resource_audit_log (
                resource_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                dataset_id TEXT,
                canonical_url TEXT NOT NULL,
                download_url TEXT,
                status TEXT NOT NULL,
                content_sha256 TEXT,
                file_size_bytes INTEGER,
                period_start TEXT,
                period_end TEXT,
                date_confidence_score TEXT,
                error_code TEXT,
                error_stackTrace TEXT,
                execution_timestamp TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    @staticmethod
    def resource_uuid(source_id: str, canonical_url: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{canonical_url}"))

    def upsert_source(self, source_id: str, name: str, base_url: str, config_path: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO source_inventory(source_id, name, base_url, config_path, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
              name=excluded.name,
              base_url=excluded.base_url,
              config_path=excluded.config_path,
              updated_at=excluded.updated_at
            """,
            (source_id, name, base_url, config_path, now),
        )
        self.conn.commit()

    def upsert_resource(
        self,
        source_id: str,
        dataset_id: str,
        canonical_url: str,
        download_url: str,
        status: str,
        resource_id: Optional[str] = None,
        content_sha256: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        date_confidence_score: Optional[str] = None,
        error_code: Optional[str] = None,
        error: Optional[BaseException] = None,
    ) -> str:
        rid = resource_id or self.resource_uuid(source_id, canonical_url)
        now = datetime.now(timezone.utc).isoformat()
        error_stack = "".join(traceback.format_exception(type(error), error, error.__traceback__)) if error else None
        self.conn.execute(
            """
            INSERT INTO resource_audit_log(
                resource_id, source_id, dataset_id, canonical_url, download_url, status,
                content_sha256, file_size_bytes, period_start, period_end, date_confidence_score,
                error_code, error_stackTrace, execution_timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(resource_id) DO UPDATE SET
              status=excluded.status,
              content_sha256=excluded.content_sha256,
              file_size_bytes=excluded.file_size_bytes,
              period_start=excluded.period_start,
              period_end=excluded.period_end,
              date_confidence_score=excluded.date_confidence_score,
              error_code=excluded.error_code,
              error_stackTrace=excluded.error_stackTrace,
              execution_timestamp=excluded.execution_timestamp
            """,
            (
                rid,
                source_id,
                dataset_id,
                canonical_url,
                download_url,
                status,
                content_sha256,
                file_size_bytes,
                period_start,
                period_end,
                date_confidence_score,
                error_code,
                error_stack,
                now,
            ),
        )
        self.conn.commit()
        return rid

    def close(self) -> None:
        self.conn.close()
