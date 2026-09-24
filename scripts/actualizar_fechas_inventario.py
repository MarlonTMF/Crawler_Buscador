"""
Actualiza las fechas y niveles de confianza de las corridas existentes sin volver a rastrear (B-50).
Aplica la jerarquía de extracción mejorada de MetadataExtractor sobre inventory.db y mapa_*.json.
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from crawler.core.control_db import ControlDatabase
from crawler.core.extractor import MetadataExtractor
from crawler.core.fetcher import HttpFetcher
from crawler.sources.generic_adapter import GenericSourceAdapter


class OfflineFetcher(HttpFetcher):
    """Fetcher simulado para re-indexación offline sin tráfico de red."""
    def fetch_head(self, url: str):
        return False, 0, {}


def reindex_source_dates(source_id: str, output_base: Path = Path("output"), dry_run: bool = False) -> Dict[str, Any]:
    db_path = output_base / source_id / "inventory.db"
    if not db_path.exists():
        print(f"[{source_id}] No existe {db_path}")
        return {}

    cfg_path = Path(f"config/source_{source_id}.yaml")
    adapter = GenericSourceAdapter(cfg_path)
    control_db = ControlDatabase(db_path)
    fetcher = OfflineFetcher()
    extractor = MetadataExtractor(fetcher, adapter)

    # Cargar mapa JSON si existe para rescatar anchor_text, context_text y last_modified previo
    mapa_path = output_base / source_id / f"mapa_{source_id}.json"
    evidence_lookup: Dict[str, Dict[str, Any]] = {}
    mapa_data: Optional[Dict[str, Any]] = None

    if mapa_path.exists():
        try:
            with open(mapa_path, "r", encoding="utf-8") as f:
                mapa_data = json.load(f)
            for ds in mapa_data.get("datasets", []):
                for res in ds.get("resources", []):
                    c_url = res.get("canonical_url")
                    if c_url:
                        ev = res.get("evidence", {})
                        meta = res.get("metadata", {})
                        evidence_lookup[c_url] = {
                            "anchor_text": ev.get("anchor_text", "") or "",
                            "context_text": ev.get("context_text", "") or "",
                            "last_modified": meta.get("last_modified") or res.get("published_at"),
                        }
        except Exception as e:
            print(f"[{source_id}] Advertencia al leer {mapa_path}: {e}")

    # Consultar todas las filas actuales del inventario
    cursor = control_db.conn.execute(
        "SELECT resource_id, canonical_url, download_url FROM resource_audit_log"
    )
    rows = cursor.fetchall()

    updated_records: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        rid = row["resource_id"]
        c_url = row["canonical_url"]
        ev_info = evidence_lookup.get(c_url, {})
        anchor = ev_info.get("anchor_text", "")
        context = ev_info.get("context_text", "")
        prev_last_mod = ev_info.get("last_modified")

        # Clasificación de dataset actualizado según reglas YAML
        new_dataset_id = adapter.classify_dataset(c_url, anchor)

        # Extraer con la lógica de 4 capas de extractor.py
        date_res, _ = extractor.resolve_date_and_metadata(
            url=c_url,
            anchor_text=anchor,
            context_text=context
        )

        # Si Capa 1 y Capa 2 no dieron published_at pero teníamos Last-Modified previo
        final_published_at = date_res.published_at
        if not final_published_at and prev_last_mod:
            final_published_at = prev_last_mod

        # Si solo tenemos published_at de carpeta o header, confianza no puede ser high
        final_confidence = date_res.confidence
        if final_published_at and not date_res.period_start:
            if final_confidence == "high":
                final_confidence = "low"

        if not dry_run:
            control_db.conn.execute(
                """
                UPDATE resource_audit_log
                SET dataset_id = ?,
                    period_start = ?,
                    period_end = ?,
                    published_at = ?,
                    date_confidence_score = ?
                WHERE resource_id = ?
                """,
                (
                    new_dataset_id,
                    date_res.period_start,
                    date_res.period_end,
                    final_published_at,
                    final_confidence,
                    rid,
                )
            )

        updated_records[c_url] = {
            "dataset_id": new_dataset_id,
            "period_start": date_res.period_start,
            "period_end": date_res.period_end,
            "published_at": final_published_at,
            "confidence": final_confidence,
            "method": date_res.method,
        }

    if not dry_run:
        control_db.conn.commit()

    # Si teníamos mapa_*.json, actualizarlo en memoria y re-exportar
    if mapa_data and not dry_run:
        for ds in mapa_data.get("datasets", []):
            for res in ds.get("resources", []):
                c_url = res.get("canonical_url")
                if c_url in updated_records:
                    up = updated_records[c_url]
                    res["period_start"] = up["period_start"]
                    res["period_end"] = up["period_end"]
                    res["published_at"] = up["published_at"]
                    res["metadata"]["date_confidence"] = up["confidence"]
                    res["metadata"]["date_extraction_method"] = up["method"]

        with open(mapa_path, "w", encoding="utf-8") as f:
            json.dump(mapa_data, f, ensure_ascii=False, indent=2)

    # Calcular estadísticas agregadas
    total_q = control_db.conn.execute("SELECT count(*) FROM resource_audit_log").fetchone()[0]
    resolved_q = control_db.conn.execute(
        "SELECT count(*) FROM resource_audit_log WHERE period_start IS NOT NULL OR published_at IS NOT NULL"
    ).fetchone()[0]
    high_q = control_db.conn.execute(
        "SELECT count(*) FROM resource_audit_log WHERE date_confidence_score = 'high'"
    ).fetchone()[0]
    folder_only_high = control_db.conn.execute(
        "SELECT count(*) FROM resource_audit_log WHERE date_confidence_score = 'high' AND period_start IS NULL AND published_at IS NOT NULL"
    ).fetchone()[0]
    conf_breakdown = control_db.conn.execute(
        "SELECT date_confidence_score, count(*) FROM resource_audit_log GROUP BY date_confidence_score"
    ).fetchall()
    dataset_breakdown = control_db.conn.execute(
        "SELECT dataset_id, count(*) FROM resource_audit_log GROUP BY dataset_id"
    ).fetchall()

    control_db.close()

    pct_resolved = (resolved_q / total_q) * 100 if total_q > 0 else 0
    stats = {
        "source_id": source_id,
        "total": total_q,
        "resolved": resolved_q,
        "pct_resolved": round(pct_resolved, 2),
        "high": high_q,
        "folder_only_high": folder_only_high,
        "breakdown": dict(conf_breakdown),
        "datasets": dict(dataset_breakdown),
    }
    return stats


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    if dry:
        print("=== MODO DRY RUN (SIN MODIFICACIONES) ===")
    for s in ["asfi", "bcb", "ine"]:
        st = reindex_source_dates(s, dry_run=dry)
        print(f"=== {s.upper()} ===")
        print(f"Total: {st.get('total')}")
        print(f"Resueltos (period_start o published_at): {st.get('resolved')} ({st.get('pct_resolved')}%)")
        print(f"High: {st.get('high')}")
        print(f"High con fecha solo de carpeta: {st.get('folder_only_high')}")
        print(f"Desglose de confianza: {st.get('breakdown')}")
        print(f"Desglose de datasets: {st.get('datasets')}\n")
