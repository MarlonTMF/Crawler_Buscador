"""
Bridge Exporter: Exportador de Recursos al Formato Canónico del Bridge (DuckDB / ResourceCandidate).

Permite conectar los hallazgos de crawler_finrural directamente con el motor de conciliación
y almacenamiento Bronze de prospector_interno vía archivo directo (sin dependencias de red).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from crawler.core.canonicalizer import Canonicalizer
from crawler.core.internal_reconciler import build_period_label

logger = logging.getLogger(__name__)

# Solo estas confianzas producen period_label en el mapa exportado.
PERIOD_CONFIDENCE_EXPORTED = {"high", "medium"}

MIME_TYPE_MAP = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "zip": "application/zip",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "json": "application/json",
    "xml": "application/xml",
}


class BridgeExporter:
    """Exporta inventarios de crawler_finrural en formato compatible con DuckDBDiffEngine de prospector_interno."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path("output/bridge")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.canonicalizer = Canonicalizer(None)

    def export_from_inventory(
        self,
        source_id: str,
        db_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        source_name: Optional[str] = None,
        base_url: Optional[str] = None,
        revalidation_path: Optional[Path] = None,
    ) -> Path:
        """
        Lee 'inventory.db' y genera el mapa estructurado para el Bridge.

        - ``period_label`` solo se emite con confianza alta o media: las fechas
          de baja confianza provienen de carpetas de publicación y el interno
          concilia por período cuando no hay huella de contenido.
        - Si se indica ``revalidation_path`` (salida de scripts/revalidar_urls.py),
          las URLs clasificadas como ELIMINADA salen con ``change_status`` REMOVED.
        """
        if db_path is None:
            db_path = Path(f"output/{source_id}/inventory.db")

        if not db_path.exists():
            raise FileNotFoundError(f"No se encontró la base de datos en '{db_path}'")

        if output_path is None:
            output_path = self.output_dir / f"external_map_{source_id}.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("""
            SELECT resource_id, canonical_url, download_url, content_sha256, file_size_bytes,
                   period_start, period_end, date_confidence_score, status, execution_timestamp
            FROM resource_audit_log
            WHERE status IN ('PROCESADO_EXITOSAMENTE', 'RECUPERADO_VIA_CONTINGENCIA', 'RECUPERADO_VIA_ESCALERA')
        """)
        rows = cur.fetchall()
        conn.close()

        eliminadas = set()
        if revalidation_path is not None and Path(revalidation_path).exists():
            reval = json.loads(Path(revalidation_path).read_text(encoding="utf-8"))
            eliminadas = {r.get("url") for r in reval.get("results", []) if r.get("status") == "ELIMINADA"}

        run_id = f"run_{source_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        resources: List[Dict[str, Any]] = []

        detected_base_url = base_url

        for row in rows:
            res_id, c_url, d_url, sha256, size_bytes, p_start, p_end, conf, status, exec_ts = row
            url = c_url or d_url
            if not url:
                continue

            if not detected_base_url:
                parsed = urlparse(url)
                if parsed.scheme and parsed.netloc:
                    detected_base_url = f"{parsed.scheme}://{parsed.netloc}"

            # Extensión y tipo MIME
            clean_path = url.split("?")[0].split("#")[0]
            ext = clean_path.rsplit(".", 1)[1].lower() if "." in clean_path else "bin"
            file_extension = f".{ext}"
            content_type = MIME_TYPE_MAP.get(ext, "application/octet-stream")

            # Período canónico, solo si la fecha es confiable
            if (conf or "").lower() in PERIOD_CONFIDENCE_EXPORTED:
                p_label, _ = build_period_label(p_start, p_end)
            else:
                p_label = None

            # Clave de recurso canónica
            key = res_id or self.canonicalizer.generate_resource_key(
                source_id=source_id,
                dataset_id=source_id,
                period_end=p_end,
                file_type=ext,
                canonical_url=url,
            )

            # Título del recurso
            title = clean_path.rsplit("/", 1)[-1] or key

            # Estado de cambio
            if url in eliminadas:
                change_status = "REMOVED"
            elif status in ("RECUPERADO_VIA_CONTINGENCIA", "RECUPERADO_VIA_ESCALERA"):
                change_status = "NEW"
            else:
                change_status = "UNCHANGED"

            resource_candidate = {
                "resource_key": key,
                "url": url,
                "source_id": source_id,
                "title": title,
                "file_extension": file_extension,
                "content_type": content_type,
                "content_length_bytes": size_bytes or 0,
                "last_modified_header": None,
                "etag": None,
                "period_label": p_label,
                "content_hash": sha256 or None,
                "change_status": change_status,
            }
            resources.append(resource_candidate)

        # Envoltorio del mapa exterior esperado por DuckDBDiffEngine
        source_doc = {
            "id": source_id,
            "name": source_name or source_id.upper(),
            "base_url": detected_base_url or f"https://www.{source_id}.org.bo",
        }

        full_map = {
            "schema_version": "1.0.0",
            "source": source_doc,
            "run": {
                "run_id": run_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "status": "success",
            },
            "datasets": [
                {
                    "id": f"{source_id}_dataset",
                    "name": f"Recursos {source_id.upper()}",
                    "resources": resources,
                }
            ],
            "total_resources": len(resources),
            "source_id": source_id,
            "run_id": run_id,
            "resources": [
                {
                    "key": r["resource_key"],
                    "url": r["url"],
                    "title": r["title"],
                    "ext": r["file_extension"],
                    "period": r["period_label"],
                    "status": r["change_status"],
                }
                for r in resources
            ],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(full_map, f, ensure_ascii=False, indent=2)

        logger.info(f"Mapa exportado para Bridge en: {output_path} ({len(resources)} recursos)")
        return output_path

    def export_from_diagnostic(
        self,
        diagnostic_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        source_filter: Optional[str] = None,
    ) -> Path:
        """
        Genera el mapa para el Bridge a partir de los documentos encontrados en 'excel_urls_diagnostic.json'.
        """
        if diagnostic_path is None:
            diagnostic_path = Path("output/excel_urls_diagnostic.json")

        if not diagnostic_path.exists():
            raise FileNotFoundError(f"No se encontró el diagnóstico en '{diagnostic_path}'")

        if output_path is None:
            src_label = source_filter or "diagnostic_all"
            output_path = self.output_dir / f"external_map_{src_label}.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(diagnostic_path, "r", encoding="utf-8") as f:
            records: List[Dict[str, Any]] = json.load(f)

        resources: List[Dict[str, Any]] = []
        source_id = source_filter or "finrural"
        run_id = f"run_{source_id}_diag_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        for item in records:
            item_source = (item.get("crawler_source") or item.get("Fuente") or "unknown").lower()
            if source_filter and item_source != source_filter.lower():
                continue

            doc_ev = item.get("Document_Evidence") or {}
            samples = doc_ev.get("samples") or []

            for sample in samples:
                url = sample.get("url")
                if not url:
                    continue

                clean_path = url.split("?")[0].split("#")[0]
                ext = clean_path.rsplit(".", 1)[1].lower() if "." in clean_path else "pdf"
                file_extension = f".{ext}"
                content_type = MIME_TYPE_MAP.get(ext, "application/pdf")
                title = sample.get("title") or clean_path.rsplit("/", 1)[-1]
                key = f"{item_source}:{clean_path.rsplit('/', 1)[-1]}"

                resources.append({
                    "resource_key": key,
                    "url": url,
                    "source_id": item_source,
                    "title": title,
                    "file_extension": file_extension,
                    "content_type": content_type,
                    "content_length_bytes": 0,
                    "last_modified_header": None,
                    "etag": None,
                    "period_label": None,
                    "content_hash": None,
                    "change_status": "NEW",
                })

        full_map = {
            "schema_version": "1.0.0",
            "source": {
                "id": source_id,
                "name": source_id.upper(),
                "base_url": "https://www.finrural.org.bo",
            },
            "run": {
                "run_id": run_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "status": "success",
            },
            "datasets": [
                {
                    "id": f"{source_id}_dataset",
                    "name": f"Recursos {source_id.upper()}",
                    "resources": resources,
                }
            ],
            "total_resources": len(resources),
            "source_id": source_id,
            "run_id": run_id,
            "resources": [
                {
                    "key": r["resource_key"],
                    "url": r["url"],
                    "title": r["title"],
                    "ext": r["file_extension"],
                    "period": r["period_label"],
                    "status": r["change_status"],
                }
                for r in resources
            ],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(full_map, f, ensure_ascii=False, indent=2)

        logger.info(f"Diagnóstico exportado para Bridge en: {output_path} ({len(resources)} recursos)")
        return output_path


def main():
    parser = argparse.ArgumentParser(description="Exporta inventarios a formato de Bridge compatible con DuckDB")
    parser.add_argument("--source", default="finrural", help="ID de la fuente (ej: finrural, asfi)")
    parser.add_argument("--db", type=Path, default=None, help="Ruta al archivo inventory.db")
    parser.add_argument("--out", type=Path, default=None, help="Ruta destino del archivo JSON exportado")
    parser.add_argument("--from-diagnostic", action="store_true", help="Exportar desde excel_urls_diagnostic.json")
    parser.add_argument("--revalidation", type=Path, default=None,
                        help="Salida de revalidar_urls.py (por defecto output/revalidacion_<fuente>.json si existe)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    exporter = BridgeExporter()

    if args.from_diagnostic:
        out = exporter.export_from_diagnostic(output_path=args.out, source_filter=args.source)
    else:
        reval = args.revalidation or Path(f"output/revalidacion_{args.source}.json")
        out = exporter.export_from_inventory(
            source_id=args.source, db_path=args.db, output_path=args.out,
            revalidation_path=reval if reval.exists() else None,
        )

    print(f"Exportación completada exitosamente: {out.resolve()}")


if __name__ == "__main__":
    main()
