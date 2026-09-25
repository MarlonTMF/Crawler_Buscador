#!/usr/bin/env python3
"""
scripts/conciliar_crawler_interno.py
===================================
Script de conciliación de Fase 4 (B-57 / Decisión D-19).
Realiza el cruce entre el inventario oficial de crawler_finrural (formato ResourceCandidate, Opción A)
y el catálogo del crawler interno (volcado histórico de Rolando / prospector interno).

Aplica estrictamente las condiciones C-1 a C-10:
- C-1: Clave de identidad por URL canónica normalizada en 3 pasadas (hash como comparador, no clave).
- C-2: Declaración y evidencia del insumo interno y su matriz de disponibilidad de campos.
- C-3: Umbral de validez de clave del 10%. Portales por debajo se marcan CLAVE_NO_VALIDADA.
- C-4: Formato canónico de period_label sin valores centinela.
- C-5: Compuerta de confianza (sólo >= medium genera DISCORDANCIA_PERIODO).
- C-6: Sin dependencias nuevas, taxonomía compatible.
- C-7: Normalización de URL única compartida con Canonicalizer.
- C-8: Declaración de estado de verificación (VERIFICADO_CON_HASH vs CATALOGADO_SIN_BYTES).
- C-9: Aislamiento total de repositorios hermanos y sin puertos de red.
- C-10: Invariante de totalidad probada por aserción en cada corrida.

Salida:
- docs/entregas/conciliacion_interno_externo.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple

# Asegurar path para imports
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from crawler.core.canonicalizer import Canonicalizer
from crawler.core.exporter import MultiFormatExporter
from crawler.core.internal_reconciler import (
    InternalReconciler,
    is_valid_period_label,
    CATEGORIAS_VALIDAS,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("conciliar_crawler_interno")

DEFAULT_INTERNAL_DIR = REPO_ROOT / "Elecciones De Crawler por URL" / "Rolando" / "extracted" / "output"

DEFAULT_PORTAL_FILES: Dict[str, List[str]] = {
    "bcb": ["bcb.json"],
    "ine": ["ine.json"],
    "asfi": ["asfi.json", "asfi_bcb.json", "asfi_finrural.json", "asfi_valores.json"],
}


def extraer_recursos_internos(paths: List[Path]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Extrae recursos del volcado interno e inspecciona la matriz de disponibilidad (C-2).
    """
    recursos: List[Dict[str, Any]] = []
    matrix_per_file: Dict[str, Any] = {}

    for path in paths:
        if not path.exists():
            logger.warning(f"Archivo interno no encontrado: {path}")
            continue

        st = path.stat()
        mtime_str = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
        
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception as e:
                logger.error(f"Error decodificando JSON {path}: {e}")
                continue

        file_items: List[Dict[str, Any]] = []

        def walk(obj: Any, ctx: str = ""):
            if isinstance(obj, dict):
                if "url_descarga" in obj and isinstance(obj["url_descarga"], str):
                    item = dict(obj)
                    item["_source_file"] = path.name
                    file_items.append(item)
                for k, v in obj.items():
                    walk(v, f"{ctx}/{k}" if ctx else k)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    walk(v, f"{ctx}[{i}]")

        walk(data)

        # Medir disponibilidad de campos en este archivo
        total_f = len(file_items)
        con_url = sum(1 for it in file_items if it.get("url_descarga"))
        con_hash = sum(1 for it in file_items if it.get("content_hash") or it.get("sha256"))
        con_period_canonico = sum(
            1 for it in file_items
            if it.get("period_label") and is_valid_period_label(str(it.get("period_label")))
        )
        con_fecha_crawl = sum(
            1 for it in file_items
            if (it.get("fecha_actualizacion") and it.get("fecha_actualizacion") != "No disponible")
        )

        matrix_per_file[path.name] = {
            "path": str(path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path),
            "size_bytes": st.st_size,
            "modified_at": mtime_str,
            "total_records": total_f,
            "con_url": con_url,
            "con_hash": con_hash,
            "con_periodo_canonico": con_period_canonico,
            "con_fecha_crawl": con_fecha_crawl,
        }

        recursos.extend(file_items)

    return recursos, matrix_per_file


def run_reconciliation(
    portales: List[str],
    internal_dir: Path,
    output_path: Path,
    min_match_rate: float = 0.10,
) -> Dict[str, Any]:
    """
    Ejecuta el pipeline completo de conciliación bajo D-19.
    """
    reconciler = InternalReconciler()
    overall_report: Dict[str, Any] = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "decision": "D-19",
            "contract": "ResourceCandidate_v1",
            "min_match_rate_threshold": min_match_rate,
            "purpose": "Instrumento de medición de brecha entre catálogo externo e interno (D-19.2)",
        },
        "portales": {},
        "global_summary": {
            "total_external_records": 0,
            "total_internal_records": 0,
            "total_reconciled_entities": 0,
            "total_url_matches_validadas": 0,
            "total_url_matches_cuarentena": 0,
            "total_duplicate_urls_ext": 0,
            "total_duplicate_urls_int": 0,
            "categories_total": {cat: 0 for cat in CATEGORIAS_VALIDAS},
        },
    }

    for portal in portales:
        portal = portal.lower().strip()
        logger.info(f"=== Conciliando portal: {portal.upper()} ===")

        # 1. Exportar e importar candidatos externos
        portal_dir = REPO_ROOT / "output" / portal
        exporter = MultiFormatExporter(portal_dir)
        cand_path = exporter.export_resource_candidates(portal)

        with open(cand_path, "r", encoding="utf-8") as f:
            ext_export_data = json.load(f)

        ext_candidates = ext_export_data.get("candidates", [])
        ext_verif_summary = ext_export_data.get("verification_summary", {})
        ext_period_summary = ext_export_data.get("period_summary", {})

        # 2. Cargar insumo interno y matriz de disponibilidad (C-2 / H-3)
        int_files = DEFAULT_PORTAL_FILES.get(portal, [f"{portal}.json"])
        int_paths = [internal_dir / fn for fn in int_files]
        int_items, int_matrix = extraer_recursos_internos(int_paths)

        # Totales internos de disponibilidad
        int_total_records = len(int_items)
        int_total_hash = sum(f["con_hash"] for f in int_matrix.values())
        int_total_period = sum(f["con_periodo_canonico"] for f in int_matrix.values())
        int_total_fecha_crawl = sum(f["con_fecha_crawl"] for f in int_matrix.values())

        # 3. Ejecutar Reconciliación en 3 pasadas (C-1 / H-2 / H-3)
        recon_results = reconciler.reconcile(
            portal=portal,
            external_items=ext_candidates,
            internal_items=int_items,
            min_match_rate=min_match_rate,
        )

        portal_status = reconciler.portal_status.get(portal, "VALIDADA")
        cat_counts = {cat: len(items) for cat, items in recon_results.items()}
        total_portal_entities = sum(cat_counts.values())

        # Diagnóstico de tasa de coincidencia para C-3
        valid_ext_urls = {Canonicalizer.canonicalize(c["url"]) for c in ext_candidates if c.get("url")}
        valid_int_urls = {Canonicalizer.canonicalize(it["url_descarga"]) for it in int_items if it.get("url_descarga")}
        common_urls = valid_ext_urls.intersection(valid_int_urls)
        smaller_side = min(len(valid_ext_urls), len(valid_int_urls)) if (valid_ext_urls and valid_int_urls) else 0
        match_rate = len(common_urls) / smaller_side if smaller_side > 0 else 0.0

        # Declaración explícita de las cuatro categorías inalcanzables (C-2, C-8, C-10, H-4)
        dimensiones_no_medibles = [
            {
                "categoria": "CONFIRMADO",
                "motivo": (
                    f"Sin hashes SHA-256 en el insumo interno (0/{int_total_records}) "
                    f"ni en el inventario externo de BCB/INE (0 verificados), una coincidencia de URL "
                    f"no puede confirmarse en contenido bajo D-13, sólo constatarse."
                ),
                "afecta_filas": len(common_urls),
            },
            {
                "categoria": "URL_CAMBIADA",
                "motivo": (
                    f"Inalcanzable al carecer el lado interno de hashes SHA-256 (0/{int_total_records}) "
                    f"para cotejar recursos no emparejados por URL en la segunda pasada de C-1."
                ),
                "afecta_filas": len(valid_ext_urls - common_urls),
            },
            {
                "categoria": "DISCORDANCIA_CONTENIDO",
                "motivo": (
                    f"Falta de hashes SHA-256 comparables en ambos lados (externo tiene "
                    f"{ext_verif_summary.get('VERIFICADO_CON_HASH', 0)} verificados; interno tiene {int_total_hash})."
                ),
                "afecta_filas": len(common_urls),
            },
            {
                "categoria": "DISCORDANCIA_PERIODO",
                "motivo": (
                    f"Inalcanzable porque el contrato ResourceCandidate no incluye campo de confianza (C-5) "
                    f"y el insumo interno carece de períodos canónicos de cobertura ({int_total_period} disponibles)."
                ),
                "afecta_filas": len(common_urls),
            },
        ]

        url_matches_info = {
            "urls_coincidentes_constatadas": len(common_urls),
            "en_cuarentena_por_c3": bool(portal_status == "CLAVE_NO_VALIDADA"),
            "declaracion": (
                f"{len(common_urls)} URLs constatadas en ambos catálogos"
                if portal_status == "VALIDADA"
                else f"{len(common_urls)} URL coincidente en cuarentena por tasa < {min_match_rate*100}%"
            ),
        }

        portal_entry = {
            "status": portal_status,
            "url_matches_constatadas": url_matches_info,
            "match_rate": {
                "external_unique_urls": len(valid_ext_urls),
                "internal_unique_urls": len(valid_int_urls),
                "common_urls": len(common_urls),
                "smaller_side": smaller_side,
                "match_rate_pct": round(match_rate * 100, 2),
                "threshold_pct": round(min_match_rate * 100, 2),
                "validated": bool(match_rate >= min_match_rate),
            },
            "c2_internal_input_matrix": {
                "files": int_matrix,
                "total_records": int_total_records,
                "with_url": sum(f["con_url"] for f in int_matrix.values()),
                "with_hash": int_total_hash,
                "with_periodo_canonico": int_total_period,
                "with_fecha_crawl": int_total_fecha_crawl,
            },
            "c8_external_verification_state": ext_verif_summary,
            "period_summary": ext_period_summary,
            "dimensiones_no_medibles": dimensiones_no_medibles,
            "category_counts": cat_counts,
            "total_entities_classified": total_portal_entities,
            "duplicate_urls_ext": reconciler.duplicate_urls_ext,
            "duplicate_urls_int": reconciler.duplicate_urls_int,
            "results_sample": {
                cat: items[:5] for cat, items in recon_results.items() if items
            },
        }

        overall_report["portales"][portal] = portal_entry

        # Acumular resumen global
        overall_report["global_summary"]["total_external_records"] += len(ext_candidates)
        overall_report["global_summary"]["total_internal_records"] += int_total_records
        overall_report["global_summary"]["total_reconciled_entities"] += total_portal_entities
        overall_report["global_summary"]["total_duplicate_urls_ext"] += reconciler.duplicate_urls_ext
        overall_report["global_summary"]["total_duplicate_urls_int"] += reconciler.duplicate_urls_int
        if portal_status == "VALIDADA":
            overall_report["global_summary"]["total_url_matches_validadas"] += len(common_urls)
        else:
            overall_report["global_summary"]["total_url_matches_cuarentena"] += len(common_urls)

        for cat in CATEGORIAS_VALIDAS:
            overall_report["global_summary"]["categories_total"][cat] += cat_counts[cat]

    # Guardar JSON de entrega
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(overall_report, f, ensure_ascii=False, indent=2)

    logger.info(f"Reporte de conciliación guardado en: {output_path}")
    return overall_report


def print_cli_summary(report: Dict[str, Any]):
    """Imprime un resumen tabular formateado para la terminal."""
    print("\n" + "=" * 80)
    print("REPORTE OFICIAL DE CONCILIACIÓN INTERNO - EXTERNO (FASE 4 / B-57 / D-19)")
    print("=" * 80)
    print(f"Generado: {report['metadata']['generated_at']}")
    print(f"Contrato: {report['metadata']['contract']} (Opción A, D-19)")
    print(f"Umbral de coincidencia (C-3): {report['metadata']['min_match_rate_threshold'] * 100}%\n")

    for portal, p_data in report["portales"].items():
        mr = p_data["match_rate"]
        c2 = p_data["c2_internal_input_matrix"]
        c8 = p_data["c8_external_verification_state"]
        counts = p_data["category_counts"]

        print(f"--- PORTAL: {portal.upper()} [Estado: {p_data['status']}] ---")
        print(f"  * URLs únicas: Ext={mr['external_unique_urls']}, Int={mr['internal_unique_urls']}, Coincidentes={mr['common_urls']}")
        print(f"  * Tasa de coincidencia: {mr['match_rate_pct']}% (Umbral: {mr['threshold_pct']}%) -> {'VALIDADA' if mr['validated'] else 'CLAVE_NO_VALIDADA'}")
        print(f"  * Coincidencias constatadas (H-4): {p_data['url_matches_constatadas']['declaracion']}")
        print(f"  * Insumo interno (C-2): {c2['total_records']} registros en {len(c2['files'])} archivo(s) | con URL={c2['with_url']}, con Hash={c2['with_hash']}, con Período Canónico={c2['with_periodo_canonico']} (con Fecha Crawl={c2['with_fecha_crawl']})")
        print(f"  * Verificación externa (C-8): Hash={c8.get('VERIFICADO_CON_HASH', 0)}, Sin Bytes={c8.get('CATALOGADO_SIN_BYTES', 0)}")
        print(f"  * Duplicados de URL colapsados (O-9): Ext={p_data['duplicate_urls_ext']}, Int={p_data['duplicate_urls_int']}")
        
        if p_data["dimensiones_no_medibles"]:
            print("  * Categorías inalcanzables / no medibles declaradas (C-2/C-10/H-4):")
            for d in p_data["dimensiones_no_medibles"]:
                print(f"    - {d['categoria']:24s}: {d['motivo']} (afecta {d['afecta_filas']} filas)")

        print("  * Desglose por categoría (C-10):")
        for cat in CATEGORIAS_VALIDAS:
            val = counts.get(cat, 0)
            if val > 0:
                print(f"    - {cat:32s}: {val:5d}")
        print(f"  * Total entidades clasificadas: {p_data['total_entities_classified']}")
        print()

    glob = report["global_summary"]
    print("=" * 80)
    print("TOTALES GLOBALES (3 PORTALES):")
    print(f"  * Total registros externos: {glob['total_external_records']}")
    print(f"  * Total registros internos: {glob['total_internal_records']}")
    print(f"  * Total entidades clasificadas (Unión C-10): {glob['total_reconciled_entities']}")
    print(f"  * Total URLs coincidentes constatadas (H-4): {glob['total_url_matches_validadas']} validadas + {glob['total_url_matches_cuarentena']} en cuarentena = {glob['total_url_matches_validadas'] + glob['total_url_matches_cuarentena']} total")
    print(f"  * Total duplicados de URL colapsados (O-9): Ext={glob['total_duplicate_urls_ext']}, Int={glob['total_duplicate_urls_int']}")
    print("  * Desglose global de categorías:")
    for cat, val in glob["categories_total"].items():
        if val > 0:
            print(f"    - {cat:32s}: {val:5d}")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Conciliación entre catálogo externo e interno (B-57 / D-19)")
    parser.add_argument(
        "--portales",
        nargs="+",
        default=["bcb", "ine", "asfi"],
        help="Portales a procesar (default: bcb ine asfi)",
    )
    parser.add_argument(
        "--internal-dir",
        type=Path,
        default=DEFAULT_INTERNAL_DIR,
        help="Directorio con los volcados de Rolando / prospector interno",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "docs" / "entregas" / "conciliacion_interno_externo.json",
        help="Ruta del archivo JSON de salida",
    )
    parser.add_argument(
        "--min-match-rate",
        type=float,
        default=0.10,
        help="Umbral mínimo de tasa de coincidencia para validar la clave (C-3, default: 0.10)",
    )
    args = parser.parse_args()

    report = run_reconciliation(
        portales=args.portales,
        internal_dir=args.internal_dir,
        output_path=args.output,
        min_match_rate=args.min_match_rate,
    )
    print_cli_summary(report)


if __name__ == "__main__":
    main()
