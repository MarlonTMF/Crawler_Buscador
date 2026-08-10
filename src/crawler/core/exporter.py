"""
Exporters multi-formato (ADR-006):
1. StandardJsonExporter: Contrato oficial estandarizado 'ExternalSourceMap' v1.0.0.
2. TreeExporter: Vista jerárquica en árbol (Niveles 1 a 5 con sufijo .csv) compatible con el prototipo BCB.
3. CompactAIExporter: Vista compacta semántica para consumo por agentes de IA.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from crawler.core.models import ExternalSourceMap
from crawler.core.reducer import AIContextReducer
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
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(compact_items, f, ensure_ascii=False, indent=2)

        logger.info(f"Vista compacta para IA guardada en: {out_path}")
        return out_path
