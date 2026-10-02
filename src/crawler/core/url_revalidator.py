"""
crawler/core/url_revalidator.py
===============================
Módulo de revalidación periódica de URLs catalogadas en el inventario (B-60 / P-1).

Realiza peticiones HTTP HEAD (con GET de respaldo ante 405) para verificar la vigencia
de los recursos documentales almacenados en resource_audit_log de cada portal.

Clasifica cada URL según la tabla formal de estados:
  - VIGENTE: 200 y tipo de contenido documental (PDF, Excel, ZIP, etc.).
  - REDIRIGIDA: 301/302/etc. hacia otra URL que responde 200 (guarda destino).
  - ELIMINADA: 404 o 410 comprobado.
  - INACCESIBLE: Timeout, 403, error TLS/conexión o 5xx (no equivale a eliminada).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
import yaml

logger = logging.getLogger(__name__)

DOCUMENTARY_MIME_TYPES = {
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
    "text/csv",
}

DOCUMENTARY_EXTENSIONS = {
    ".pdf", ".xlsx", ".xls", ".csv", ".zip", ".rar", ".7z", ".ods", ".doc", ".docx"
}


@dataclass
class UrlRevalidationResult:
    url: str
    source: str
    status: str  # VIGENTE, REDIRIGIDA, ELIMINADA, INACCESIBLE
    http_status: Optional[int] = None
    final_url: Optional[str] = None
    content_type: Optional[str] = None
    error_message: Optional[str] = None
    revalidated_at: str = ""
    dataset_id: Optional[str] = None
    resource_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class UrlRevalidator:
    """Revalidador de URLs catalogadas por fuente contra inventory.db."""

    def __init__(
        self,
        base_output_dir: Optional[Path] = None,
        config_dir: Optional[Path] = None,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ProspectorExterno/1.0",
        timeout: int = 10,
        rate_limit_override: Optional[float] = None,
    ):
        self.base_output_dir = Path(base_output_dir or "output")
        self.config_dir = Path(config_dir or "config")
        self.user_agent = user_agent
        self.timeout = timeout
        self.rate_limit_override = rate_limit_override

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        # Deshabilitar verificación SSL para portales gubernamentales con cadenas incompletas
        self.session.verify = False
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    def get_source_rate_limit(self, source: str) -> float:
        """Obtiene la tasa de peticiones por segundo configurada para la fuente."""
        if self.rate_limit_override is not None:
            return float(self.rate_limit_override)

        yaml_path = self.config_dir / f"source_{source}.yaml"
        if yaml_path.exists():
            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                    rate = cfg.get("crawl", {}).get("rate_limit_per_second")
                    if rate and float(rate) > 0:
                        return float(rate)
            except Exception as e:
                logger.debug("Error leyendo rate_limit de %s: %s", yaml_path, e)

        return 1.0

    def is_documentary(self, content_type: Optional[str], url: str) -> bool:
        """Determina si el recurso tiene tipo de contenido documental."""
        if content_type:
            ct = content_type.lower().split(";")[0].strip()
            if ct in DOCUMENTARY_MIME_TYPES:
                return True
            if ct == "text/html":
                return False

        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        return any(path_lower.endswith(ext) for ext in DOCUMENTARY_EXTENSIONS)

    def check_url(
        self,
        url: str,
        source: str = "",
        dataset_id: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> UrlRevalidationResult:
        """Ejecuta HEAD (o GET de respaldo) y clasifica el estado de la URL."""
        timestamp = datetime.now(timezone.utc).isoformat()

        try:
            resp = self.session.head(
                url,
                timeout=self.timeout,
                allow_redirects=True,
            )

            # Si el servidor rechaza HEAD con 405 Method Not Allowed, intentar GET en streaming
            if resp.status_code == 405:
                resp = self.session.get(
                    url,
                    timeout=self.timeout,
                    allow_redirects=True,
                    stream=True,
                )

            status_code = resp.status_code
            content_type = resp.headers.get("Content-Type", "")
            final_url = str(resp.url)

            # Evaluar redirecciones
            has_redirect = False
            if resp.history:
                # Comprobar si realmente hubo cambio de URL efectiva
                if final_url.rstrip("/") != url.rstrip("/"):
                    has_redirect = True

            if status_code == 200:
                if has_redirect:
                    return UrlRevalidationResult(
                        url=url,
                        source=source,
                        status="REDIRIGIDA",
                        http_status=status_code,
                        final_url=final_url,
                        content_type=content_type,
                        revalidated_at=timestamp,
                        dataset_id=dataset_id,
                        resource_id=resource_id,
                    )
                else:
                    if self.is_documentary(content_type, final_url):
                        return UrlRevalidationResult(
                            url=url,
                            source=source,
                            status="VIGENTE",
                            http_status=status_code,
                            final_url=final_url,
                            content_type=content_type,
                            revalidated_at=timestamp,
                            dataset_id=dataset_id,
                            resource_id=resource_id,
                        )
                    else:
                        return UrlRevalidationResult(
                            url=url,
                            source=source,
                            status="INACCESIBLE",
                            http_status=status_code,
                            final_url=final_url,
                            content_type=content_type,
                            error_message=f"Respuesta 200 pero contenido no documental ({content_type})",
                            revalidated_at=timestamp,
                            dataset_id=dataset_id,
                            resource_id=resource_id,
                        )

            elif status_code in (404, 410):
                return UrlRevalidationResult(
                    url=url,
                    source=source,
                    status="ELIMINADA",
                    http_status=status_code,
                    final_url=final_url,
                    content_type=content_type,
                    revalidated_at=timestamp,
                    dataset_id=dataset_id,
                    resource_id=resource_id,
                )

            elif status_code in (301, 302, 303, 307, 308):
                # Redirección que no resolvió a 200
                loc = resp.headers.get("Location")
                return UrlRevalidationResult(
                    url=url,
                    source=source,
                    status="REDIRIGIDA",
                    http_status=status_code,
                    final_url=loc or final_url,
                    content_type=content_type,
                    revalidated_at=timestamp,
                    dataset_id=dataset_id,
                    resource_id=resource_id,
                )

            else:
                # 403, 500, 502, 503, 504 u otros códigos no concluyentes
                return UrlRevalidationResult(
                    url=url,
                    source=source,
                    status="INACCESIBLE",
                    http_status=status_code,
                    final_url=final_url,
                    content_type=content_type,
                    error_message=f"HTTP {status_code}",
                    revalidated_at=timestamp,
                    dataset_id=dataset_id,
                    resource_id=resource_id,
                )

        except requests.exceptions.RequestException as e:
            err_msg = str(e)
            return UrlRevalidationResult(
                url=url,
                source=source,
                status="INACCESIBLE",
                http_status=None,
                final_url=None,
                content_type=None,
                error_message=f"{type(e).__name__}: {err_msg[:200]}",
                revalidated_at=timestamp,
                dataset_id=dataset_id,
                resource_id=resource_id,
            )

    def load_inventory_urls(self, source: str) -> List[Dict[str, Any]]:
        """Carga las URLs de resource_audit_log en inventory.db para la fuente."""
        db_path = self.base_output_dir / source / "inventory.db"
        if not db_path.exists():
            logger.warning("No existe base de datos de inventario en: %s", db_path)
            return []

        rows_data = []
        with sqlite3.connect(db_path) as conn:
            cols = [c[1] for c in conn.execute("PRAGMA table_info(resource_audit_log)").fetchall()]
            has_dataset_id = "dataset_id" in cols
            query = (
                "SELECT resource_id, canonical_url, dataset_id FROM resource_audit_log WHERE canonical_url IS NOT NULL"
                if has_dataset_id
                else "SELECT resource_id, canonical_url, NULL FROM resource_audit_log WHERE canonical_url IS NOT NULL"
            )
            cursor = conn.execute(query)
            for r_id, url, d_id in cursor.fetchall():
                if url:
                    rows_data.append({
                        "resource_id": r_id,
                        "canonical_url": url,
                        "dataset_id": d_id,
                    })

        return rows_data

    def revalidate_source(
        self,
        source: str,
        output_file: Optional[Path] = None,
        progress_callback: Optional[Any] = None,
        force: bool = False,
    ) -> Tuple[Path, Dict[str, Any]]:
        """Revalida todas las URLs catalogadas para una fuente específica."""
        items = self.load_inventory_urls(source)
        rate_limit = self.get_source_rate_limit(source)
        delay = (1.0 / rate_limit) if rate_limit > 0 else 0.0

        if output_file is None:
            out_dir = self.base_output_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            output_file = out_dir / f"revalidacion_{source}.json"

        if not force and output_file.exists():
            try:
                cached_data = json.loads(output_file.read_text(encoding="utf-8"))
                if cached_data.get("total_urls") == len(items) and "summary" in cached_data:
                    logger.info("Cargando revalidación existente para %s (%d URLs)", source, len(items))
                    return output_file, cached_data["summary"]
            except Exception as e:
                logger.debug("Error leyendo resultado previo de %s: %s", output_file, e)

        results: List[UrlRevalidationResult] = []
        summary = {
            "total_urls": len(items),
            "VIGENTE": 0,
            "REDIRIGIDA": 0,
            "ELIMINADA": 0,
            "INACCESIBLE": 0,
        }

        logger.info(
            "Iniciando revalidación para %s: %d URLs (rate_limit=%.2f req/s)",
            source,
            len(items),
            rate_limit,
        )

        for idx, item in enumerate(items):
            url = item["canonical_url"]
            res = self.check_url(
                url=url,
                source=source,
                dataset_id=item["dataset_id"],
                resource_id=item["resource_id"],
            )
            results.append(res)
            summary[res.status] = summary.get(res.status, 0) + 1

            if progress_callback:
                progress_callback(idx + 1, len(items), res)

            if delay > 0 and idx < len(items) - 1:
                time.sleep(delay)

        out_data = {
            "source": source,
            "revalidated_at": datetime.now(timezone.utc).isoformat(),
            "total_urls": len(items),
            "rate_limit_per_second": rate_limit,
            "summary": summary,
            "results": [r.to_dict() for r in results],
        }

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps(out_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info(
            "Revalidación completada para %s: %s (guardado en %s)",
            source,
            summary,
            output_file,
        )
        return output_file, summary
