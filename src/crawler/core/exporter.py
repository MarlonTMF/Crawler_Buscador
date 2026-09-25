"""
Exporters multi-formato (ADR-006):
1. StandardJsonExporter: Contrato oficial estandarizado 'ExternalSourceMap' v1.0.0.
2. TreeExporter: Vista jerárquica en árbol (Niveles 1 a 5 con sufijo .csv) compatible con el prototipo BCB.
3. CompactAIExporter: Vista compacta semántica para consumo por agentes de IA.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Dict, Any, List, Optional, Tuple
from crawler.core.models import ExternalSourceMap
from crawler.core.reducer import AIContextReducer
from crawler.core.canonicalizer import Canonicalizer
from crawler.core.internal_reconciler import build_period_label
from crawler.validators.schema_validator import SchemaValidator

logger = logging.getLogger(__name__)


class MultiFormatExporter:
    """Clase administradora de la exportación en los tres formatos requeridos."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.validator = SchemaValidator()
        self.reducer = AIContextReducer()

    def export_standard(self, source_map: ExternalSourceMap, filename: str = "mapa_finrural.json") -> Path:
        """
        Exporta el contrato oficial estandarizado y valida contra JSON Schema.
        """
        data = source_map.model_dump(mode="json")
        is_valid, err_msg = self.validator.validate(data)
        if not is_valid:
            logger.error(f"Error al validar esquema JSON estandarizado: {err_msg}")
            raise ValueError(f"Contrato JSON inválido contra el esquema formal: {err_msg}")

        out_path = self.output_dir / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Contrato estandarizado guardado con éxito en: {out_path}")
        return out_path

    def export_tree_format(self, source_map: ExternalSourceMap, filename: str = "mapa_finrural_tree.json") -> Path:
        """
        Exporta la estructura jerárquica en árbol (estilo example_mapa_global_bcb.json).
        
        Nivel 1: Nombre de la Fuente (ej. FINRURAL)
        Nivel 2: Nombre del Dataset (ej. Reporte_Financiero_Mensual)
        Nivel 3: Gestión / Período (ej. Gestion_2026)
        Nivel 4: Sub-nivel / Categoría (ej. REPORTE_MENSUAL)
        Nivel 5: Nombre_Documento.csv -> { "descripcion": "...", "url_descarga": "..." }
        """
        tree: Dict[str, Any] = {}
        source_key = source_map.source.name.upper()
        tree[source_key] = {}

        for dataset in source_map.datasets:
            ds_key = dataset.name.replace(" ", "_")
            if ds_key not in tree[source_key]:
                tree[source_key][ds_key] = {}

            for res in dataset.resources:
                # Extraer año o asignación de nivel 3
                year_str = "VARIOS"
                if res.period_end:
                    year_str = f"Gestion_{res.period_end[:4]}"
                elif "202" in res.download_url:
                    parts = [p for p in res.download_url.split("/") if "202" in p]
                    if parts:
                        year_str = f"Gestion_{parts[0]}"

                if year_str not in tree[source_key][ds_key]:
                    tree[source_key][ds_key][year_str] = {}

                nivel4 = "REPORTE_MENSUAL"
                if nivel4 not in tree[source_key][ds_key][year_str]:
                    tree[source_key][ds_key][year_str][nivel4] = {}

                # Limpieza del título: remueve query strings como ?x16877 y fuerza sufijo .csv
                clean_title_raw = res.title.split("?")[0].strip()
                clean_title = clean_title_raw.replace(" ", "_").replace("/", "_").replace("\\", "_")
                if not clean_title.lower().endswith(".csv"):
                    clean_title = f"{clean_title}.csv"

                tree[source_key][ds_key][year_str][nivel4][clean_title] = {
                    "descripcion": clean_title_raw,
                    "url_descarga": res.download_url
                }

        out_path = self.output_dir / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(tree, f, ensure_ascii=False, indent=4)

        logger.info(f"Vista jerárquica tipo BCB guardada en: {out_path}")
        return out_path

    def export_compact_ai(self, source_map: ExternalSourceMap, filename: str = "mapa_finrural_compact.json") -> Path:
        """
        Exporta la lista reducida de recursos optimizada para modelos de IA.
        """
        compact_items: List[Dict[str, Any]] = []

        for dataset in source_map.datasets:
            for res in dataset.resources:
                compact_item = self.reducer.build_compact_item(
                    source_id=source_map.source.id,
                    dataset_id=dataset.id,
                    resource=res
                )
                compact_items.append(compact_item)

        out_path = self.output_dir / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(compact_items, f, ensure_ascii=False, indent=2)

        logger.info(f"Vista compacta para IA guardada en: {out_path}")
        return out_path

    def export_resource_candidates(
        self,
        source_id: str,
        db_path: Optional[Path] = None,
        filename: str = "resource_candidates.json",
    ) -> Path:
        """
        Exporta el catálogo en el formato ResourceCandidate para Prospector-Externo (Opción A, D-19).
        Declara el estado de verificación explícito (VERIFICADO_CON_HASH vs CATALOGADO_SIN_BYTES, C-8)
        y emite period_label canónico estricto sin valores centinela (C-4).
        """
        if db_path is None:
            db_path = self.output_dir / "inventory.db"

        candidates: List[Dict[str, Any]] = []
        sidecar: Dict[str, Any] = {}
        omission_counts: Dict[str, int] = {}
        verif_counts = {"VERIFICADO_CON_HASH": 0, "CATALOGADO_SIN_BYTES": 0}
        label_counts = {"CON_ETIQUETA_CANONICA": 0, "SIN_ETIQUETA": 0}

        if db_path.exists():
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("""
                SELECT canonical_url, download_url, content_sha256, file_size_bytes,
                       period_start, period_end, date_confidence_score, status
                FROM resource_audit_log
                WHERE status IN ('PROCESADO_EXITOSAMENTE', 'RECUPERADO_VIA_CONTINGENCIA')
            """)
            rows = cur.fetchall()
            conn.close()

            canonicalizer = Canonicalizer(None)

            for r in rows:
                c_url, d_url, sha256, size_bytes, p_start, p_end, conf, status = r
                url = c_url or d_url

                # Extensión y tipo mime
                path_clean = url.split("?")[0].split("#")[0]
                ext = path_clean.rsplit(".", 1)[1].lower() if "." in path_clean else "bin"
                mime_map = {
                    "pdf": "application/pdf",
                    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "xls": "application/vnd.ms-excel",
                    "csv": "text/csv",
                    "zip": "application/zip",
                    "ods": "application/vnd.oasis.opendocument.spreadsheet",
                }
                content_type = mime_map.get(ext, "application/octet-stream")

                # period_label canónico (C-4)
                p_label, omission_reason = build_period_label(p_start, p_end)
                if p_label is not None:
                    label_counts["CON_ETIQUETA_CANONICA"] += 1
                else:
                    label_counts["SIN_ETIQUETA"] += 1
                    if omission_reason:
                        omission_counts[omission_reason] = omission_counts.get(omission_reason, 0) + 1

                # Estado de verificación bajo D-13 / C-8
                is_verified = bool(sha256 and size_bytes and size_bytes > 0)
                verif_status = "VERIFICADO_CON_HASH" if is_verified else "CATALOGADO_SIN_BYTES"
                verif_counts[verif_status] += 1

                # Clave de recurso
                res_key = canonicalizer.generate_resource_key(
                    source_id=source_id,
                    dataset_id=source_id,
                    period_end=p_end,
                    file_type=ext,
                    canonical_url=url,
                )

                # Nombre o título base
                name_part = path_clean.rsplit("/", 1)[-1]

                candidate = {
                    "resource_key": res_key,
                    "url": url,
                    "source_id": source_id,
                    "title": name_part,
                    "file_extension": ext,
                    "content_type": content_type,
                    "content_length_bytes": size_bytes or 0,
                    "period_label": p_label,  # None si no hay cubo canónico (C-4)
                    "content_hash": sha256 or None,
                    "verification_status": verif_status,
                }
                candidates.append(candidate)

                sidecar[url] = {
                    "confidence": conf or "unknown",
                    "period_start": p_start,
                    "period_end": p_end,
                    "omission_reason": omission_reason,
                    "audit_status": status,
                }

        out_data = {
            "source_id": source_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "contract_schema": "ResourceCandidate_v1",
            "total_records": len(candidates),
            "verification_summary": verif_counts,
            "period_summary": {
                **label_counts,
                "motivos_omision": omission_counts,
            },
            "candidates": candidates,
            "sidecar": sidecar,
        }

        out_path = self.output_dir / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Candidatos de recurso exportados en: {out_path} ({len(candidates)} filas)")
        return out_path

