#!/usr/bin/env python3
"""
scripts/correr_lote.py
======================
Runner por lotes para el prospector externo (Etapa C / B-13).

Ejecuta el pipeline de extracción (CrawlOrchestrator) para un conjunto de fuentes,
registra la ejecución en tiempo real (compatible con ejecución en segundo plano),
consulta la base de control SQLite (inventory.db) para cada fuente y genera un
reporte de cobertura consolidado en Markdown y JSON.

Uso:
    python scripts/correr_lote.py --fuentes finrural
    python scripts/correr_lote.py --fuentes finrural,bbv
    python scripts/correr_lote.py --fuentes all --max-pages 50
"""

import sys
import os
import argparse
import logging
import sqlite3
import time
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Asegurar que 'src' esté en PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from crawler.main import load_adapter
from crawler.core.orchestrator import CrawlOrchestrator
from crawler.core.models import ExternalSourceMap


def setup_batch_logging(log_file: Path, verbose: bool = False) -> logging.Logger:
    """Configura logging simultáneo a consola y a archivo de log persistente."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger("correr_lote")
    logger.setLevel(level)

    # Limpiar handlers previos
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Stream Handler (consola)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File Handler (archivo en disco para monitoreo en segundo plano)
    fh = logging.FileHandler(str(log_file), mode="w", encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger


def resolve_source_configs(
    source_identifiers: List[str],
    config_dir: Path
) -> List[Tuple[str, Optional[Path]]]:
    """
    Resuelve la ruta del archivo de configuración YAML para cada identificador de fuente.
    Soporta:
      - 'all': todos los archivos source_*.yaml en config_dir
      - nombre corto: 'finrural' -> config/source_finrural.yaml o config/finrural.yaml
      - ruta directa: 'config/source_finrural.yaml'
    """
    resolved: List[Tuple[str, Optional[Path]]] = []

    if len(source_identifiers) == 1 and source_identifiers[0].strip().lower() == "all":
        yaml_files = sorted(config_dir.glob("source_*.yaml"))
        for yf in yaml_files:
            sid = yf.stem.replace("source_", "")
            resolved.append((sid, yf))
        return resolved

    for item in source_identifiers:
        token = item.strip()
        if not token:
            continue

        # 1. Ruta directa si existe
        direct_path = Path(token)
        if direct_path.exists() and direct_path.is_file():
            sid = direct_path.stem.replace("source_", "")
            resolved.append((sid, direct_path))
            continue

        # 2. Búsqueda en config_dir
        candidate1 = config_dir / f"source_{token.lower()}.yaml"
        candidate2 = config_dir / f"{token.lower()}.yaml"

        if candidate1.exists():
            resolved.append((token, candidate1))
        elif candidate2.exists():
            resolved.append((token, candidate2))
        else:
            resolved.append((token, None))

    return resolved


def inspect_inventory_db(
    db_path: Path,
    allowed_extensions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Consulta exhaustiva de inventory.db para métricas del reporte:
    - total de registros en resource_audit_log
    - documentos reales (extensión en allowed_extensions: pdf, xlsx, xls, csv, zip)
    - otros recursos (sidecars .sha, URLs sin extensión, heurística de ruta)
    - desglose por status
    - desglose de errores por error_code
    - desglose por tipo de archivo / extensión
    - desglose por dataset_id
    """
    default_exts = {"pdf", "xlsx", "xls", "csv", "zip"}
    if allowed_extensions:
        doc_exts = {e.lower().lstrip(".") for e in allowed_extensions}
    else:
        doc_exts = default_exts

    if not db_path.exists():
        return {
            "exists": False,
            "total_records": 0,
            "documents_count": 0,
            "other_resources_count": 0,
            "status_counts": {},
            "error_counts": {},
            "extension_counts": {},
            "dataset_counts": {},
        }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Total
        cursor.execute("SELECT count(*) FROM resource_audit_log")
        total_records = cursor.fetchone()[0]

        # Status breakdown
        cursor.execute("SELECT status, count(*) FROM resource_audit_log GROUP BY status")
        status_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # Errors breakdown
        cursor.execute(
            "SELECT error_code, count(*) FROM resource_audit_log "
            "WHERE error_code IS NOT NULL AND error_code != '' GROUP BY error_code"
        )
        error_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # Dataset breakdown
        cursor.execute(
            "SELECT coalesce(dataset_id, 'sin_dataset'), count(*) "
            "FROM resource_audit_log GROUP BY dataset_id"
        )
        dataset_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # Extensions & Document classification breakdown
        cursor.execute("SELECT canonical_url, download_url, status FROM resource_audit_log")
        extension_counts: Dict[str, int] = {}
        documents_count = 0
        other_resources_count = 0

        for row in cursor.fetchall():
            url_str = (row["canonical_url"] or row["download_url"] or "").split("?")[0].split("#")[0]
            ext = Path(url_str).suffix.lower()
            ext_clean = ext.lstrip(".")

            # Si el último segmento no tiene extensión pero el path contiene .<ext>/ o termina en .<ext>
            # (típico en CMS como Liferay de BCP: /documents/.../informe.pdf/uuid)
            if not ext_clean or ext_clean not in doc_exts:
                url_lower = url_str.lower()
                for candidate_ext in doc_exts:
                    pattern = f".{candidate_ext}"
                    if f"{pattern}/" in url_lower or url_lower.endswith(pattern):
                        ext = pattern
                        ext_clean = candidate_ext
                        break

            if not ext or len(ext) > 7:
                ext_key = "otro / sin_extension"
            else:
                ext_key = ext
            extension_counts[ext_key] = extension_counts.get(ext_key, 0) + 1

            if row["status"] == "PROCESADO_EXITOSAMENTE":
                if ext_clean in doc_exts:
                    documents_count += 1
                else:
                    other_resources_count += 1

        return {
            "exists": True,
            "total_records": total_records,
            "documents_count": documents_count,
            "other_resources_count": other_resources_count,
            "status_counts": status_counts,
            "error_counts": error_counts,
            "extension_counts": extension_counts,
            "dataset_counts": dataset_counts,
        }
    except Exception as exc:
        return {
            "exists": True,
            "total_records": 0,
            "documents_count": 0,
            "other_resources_count": 0,
            "error_inspecting": str(exc),
            "status_counts": {},
            "error_counts": {},
            "extension_counts": {},
            "dataset_counts": {},
        }
    finally:
        conn.close()



def generate_markdown_report(
    batch_meta: Dict[str, Any],
    results: List[Dict[str, Any]],
    report_path: Path,
) -> str:
    """Genera el reporte formal de cobertura en formato Markdown."""
    now_str = batch_meta["finished_at"]
    total_sources = len(results)
    successful_sources = sum(1 for r in results if r.get("success", False))
    failed_sources = total_sources - successful_sources
    total_documents = sum(r.get("documents_count", 0) for r in results)
    total_other_resources = sum(r.get("other_resources_count", 0) for r in results)
    total_resources = total_documents + total_other_resources
    total_errors = sum(r.get("resources_error", 0) for r in results)
    total_duration = batch_meta.get("total_duration_seconds", 0.0)

    lines = [
        f"# Reporte de Ejecución por Lotes — Prospector Externo DataX",
        "",
        f"- **Fecha de Ejecución:** {batch_meta.get('started_at', 'N/A')} a {now_str}",
        f"- **Duración Total:** {total_duration:.2f} segundos ({total_duration/60:.2f} min)",
        f"- **Fuentes Ejecutadas:** {total_sources} (Exitosas: {successful_sources}, Fallidas: {failed_sources})",
        f"- **Total Documentos Reales (allowed_extensions):** {total_documents}",
        f"- **Total Otros Recursos (sidecars/rutas):** {total_other_resources}",
        f"- **Total Errores de Recurso:** {total_errors}",
        f"- **Archivo de Log:** `{batch_meta.get('log_file_relative', 'N/A')}`",
        "",
        "---",
        "",
        "## 1. Resumen Ejecutivo por Fuente",
        "",
        "| Fuente | Adaptador | Headless (Playwright) | Estado Lote | Documentos Reales | Otros Recursos | Errores | Tasa Doc | Duración | Top Extensión | Criterio (≥1 Doc) |",
        "|:-------|:----------|:---------------------:|:-----------:|:-----------------:|:--------------:|:-------:|:--------:|:--------:|:--------------|:------------------:|",
    ]

    for r in results:
        fid = r.get("source_id", "desconocido")
        adapter_name = r.get("adapter_name", "N/A")
        use_pw = "Sí (domcontentloaded)" if r.get("use_playwright", False) else "No (HTTP)"
        status_batch = "**ÉXITO**" if r.get("success", False) else "**FALLO**"
        docs_ok = r.get("documents_count", 0)
        others_ok = r.get("other_resources_count", 0)
        res_err = r.get("resources_error", 0)
        total_cand = docs_ok + others_ok + res_err
        doc_rate = f"{(docs_ok / total_cand * 100):.1f}%" if total_cand > 0 else "0.0%"
        dur = f"{r.get('duration_seconds', 0.0):.1f}s"
        crit_tag = "✅ CUMPLE" if r.get("meets_criteria", False) else "❌ NO CUMPLE"

        exts = r.get("db_metrics", {}).get("extension_counts", {})
        if exts:
            top_ext = sorted(exts.items(), key=lambda x: x[1], reverse=True)[0]
            top_ext_str = f"{top_ext[0]} ({top_ext[1]})"
        else:
            top_ext_str = "ninguna"

        lines.append(
            f"| `{fid}` | {adapter_name} | {use_pw} | {status_batch} | {docs_ok} | {others_ok} | {res_err} | {doc_rate} | {dur} | {top_ext_str} | {crit_tag} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 2. Detalle Exhaustivo de Auditoría (inventory.db)",
        "",
    ])

    for r in results:
        fid = r.get("source_id", "desconocido")
        inst = r.get("institution", fid)
        lines.append(f"### Fuente: `{fid}` — {inst}")
        lines.append("")
        lines.append(f"- **URL Base:** {r.get('base_url', 'N/A')}")
        lines.append(f"- **Configuración:** `{r.get('config_path', 'N/A')}`")
        lines.append(f"- **Adaptador de Clase:** `{r.get('adapter_class', 'N/A')}`")
        lines.append(f"- **Usa Playwright Headless:** {r.get('use_playwright', False)}")
        lines.append(f"- **Duración:** {r.get('duration_seconds', 0.0):.2f}s")

        if not r.get("success", False):
            lines.append(f"- **Error Fatal de Lote:** `{r.get('error_message', 'Error desconocido')}`")
            lines.append("")
            continue

        db = r.get("db_metrics", {})
        lines.append(f"- **Total Registros Auditados en DB:** {db.get('total_records', 0)}")
        lines.append(f"- **Documentos Reales Catalogados:** {r.get('documents_count', 0)}")
        lines.append(f"- **Otros Recursos (sidecars/rutas):** {r.get('other_resources_count', 0)}")
        
        # Desglose de estados
        lines.append("- **Estados en `resource_audit_log`:**")
        status_counts = db.get("status_counts", {})
        if status_counts:
            for s, c in sorted(status_counts.items()):
                lines.append(f"  - `{s}`: {c}")
        else:
            lines.append("  - *(sin registros)*")

        # Errores
        error_counts = db.get("error_counts", {})
        if error_counts:
            lines.append("- **Errores por `error_code`:**")
            for e, c in sorted(error_counts.items()):
                lines.append(f"  - `{e}`: {c}")
        else:
            lines.append("- **Errores por `error_code`:** 0 errores")

        # Extensiones
        ext_counts = db.get("extension_counts", {})
        if ext_counts:
            lines.append("- **Desglose de Archivos por Extensión:**")
            for ext, c in sorted(ext_counts.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  - `{ext}`: {c}")

        # Datasets
        ds_counts = db.get("dataset_counts", {})
        if ds_counts:
            lines.append("- **Recursos por Dataset ID:**")
            for ds_id, c in sorted(ds_counts.items()):
                lines.append(f"  - `{ds_id}`: {c}")

        # Archivos generados
        lines.append("- **Artefactos en Disco:**")
        lines.append(f"  - Base SQLite de control: `{r.get('inventory_db_path', 'N/A')}`")
        lines.append(f"  - Exportación JSON: `{r.get('map_json_path', 'N/A')}`")
        lines.append("")

    # Verificación de criterios
    lines.extend([
        "---",
        "",
        "## 3. Verificación de Criterios de Aceptación (Etapa C)",
        "",
        "El criterio de aceptación de una fuente es **≥ 1 documento real procesado exitosamente** "
        "(extensión en `allowed_extensions`: `.pdf`, `.xlsx`, `.xls`, `.csv`, `.zip`) y 0 errores fatales.",
        "",
    ])

    for r in results:
        fid = r.get("source_id", "desconocido")
        d_ok = r.get("documents_count", 0)
        o_ok = r.get("other_resources_count", 0)
        err = r.get("resources_error", 0)
        passed = r.get("meets_criteria", False)
        status_icon = "✅ APROBADO" if passed else "❌ REPROBADO"
        lines.append(f"- **Fuente `{fid}`:**")
        lines.append(f"  - Documentos reales (`allowed_extensions`): **{d_ok}**")
        lines.append(f"  - Otros recursos (sidecars/rutas): **{o_ok}**")
        lines.append(f"  - Errores de recurso: **{err}**")
        lines.append(f"  - **Resultado:** {status_icon} ({'cumple' if passed else 'no cumple'} con ≥ 1 documento real)")

    lines.append("")
    report_text = "\n".join(lines)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")
    return report_text



def main() -> None:
    parser = argparse.ArgumentParser(
        description="Runner por lotes con reporte de cobertura e inspección de inventory.db — DataX Web Prospector"
    )
    parser.add_argument(
        "--fuentes",
        type=str,
        required=True,
        help="Lista de fuentes separadas por coma (ej. 'finrural' o 'finrural,bbv' o 'all')"
    )
    parser.add_argument(
        "--config-dir",
        type=str,
        default=str(PROJECT_ROOT / "config"),
        help="Directorio con los archivos de configuración YAML (default: config/)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(PROJECT_ROOT / "output"),
        help="Directorio base para la salida del crawler (default: output/)"
    )
    parser.add_argument(
        "--reporte-dir",
        type=str,
        default=str(PROJECT_ROOT / "output" / "reportes_lotes"),
        help="Directorio para reportes consolidados (default: output/reportes_lotes/)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Override opcional para max_pages en crawl"
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=None,
        help="Override opcional para rate_limit_per_second"
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Ruta específica para archivo de log"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Generar también reporte estructurado en formato JSON"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Habilitar log DEBUG"
    )

    args = parser.parse_args()

    config_dir = Path(args.config_dir)
    output_dir = Path(args.output_dir)
    reporte_dir = Path(args.reporte_dir)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = Path(args.log_file) if args.log_file else (reporte_dir / f"lote_{timestamp_str}.log")
    logger = setup_batch_logging(log_path, verbose=args.verbose)

    logger.info("================================================================================")
    logger.info("Iniciando Runner por Lotes — DataX Web Prospector (Etapa C / B-13)")
    logger.info("================================================================================")
    logger.info("Fuentes solicitadas: %s", args.fuentes)
    logger.info("Directorio de configuración: %s", config_dir)
    logger.info("Directorio de salida: %s", output_dir)
    logger.info("Archivo de log: %s", log_path)

    # 1. Parsear e identificar fuentes
    raw_fuentes = [f.strip() for f in args.fuentes.split(",") if f.strip()]
    resolved_sources = resolve_source_configs(raw_fuentes, config_dir)

    if not resolved_sources:
        logger.error("No se encontraron fuentes válidas para ejecutar.")
        sys.exit(1)

    batch_start = datetime.now(timezone.utc)
    batch_start_iso = batch_start.isoformat()
    t_batch_0 = time.time()

    results: List[Dict[str, Any]] = []

    # 2. Ejecutar cada fuente secuencialmente
    for idx, (source_id, cfg_path) in enumerate(resolved_sources, 1):
        logger.info("--------------------------------------------------------------------------------")
        logger.info("[%d/%d] Procesando fuente: %s", idx, len(resolved_sources), source_id)
        logger.info("--------------------------------------------------------------------------------")

        if cfg_path is None or not cfg_path.exists():
            logger.error("Archivo de configuración para '%s' no encontrado. Omitiendo...", source_id)
            results.append({
                "source_id": source_id,
                "institution": source_id,
                "success": False,
                "error_message": f"Configuración YAML no encontrada en {config_dir}",
                "duration_seconds": 0.0,
                "resources_processed": 0,
                "resources_error": 0,
            })
            continue

        source_t0 = time.time()
        try:
            adapter = load_adapter(cfg_path)
            logger.info("Adaptador cargado: %s (%s)", adapter.__class__.__name__, adapter.source_name)

            # Aplicar overrides si fueron especificados por CLI
            if args.max_pages is not None:
                adapter.config.setdefault("crawl", {})["max_pages"] = args.max_pages
                logger.info("Override CLI aplicado: crawl.max_pages = %d", args.max_pages)
            if args.rate_limit is not None:
                adapter.config.setdefault("crawl", {})["rate_limit_per_second"] = args.rate_limit
                logger.info("Override CLI aplicado: crawl.rate_limit_per_second = %.2f", args.rate_limit)

            use_pw = getattr(adapter, "use_playwright", False)
            logger.info("Configuración Headless Playwright: %s", "ACTIVA" if use_pw else "INACTIVA (HTTP)")

            # Instanciar y correr Orchestrator
            orchestrator = CrawlOrchestrator(adapter=adapter, output_dir=output_dir)
            source_map = orchestrator.run()
            elapsed_source = time.time() - source_t0

            # Inspeccionar la base de datos de control inventory.db
            db_path = orchestrator.source_output_dir / "inventory.db"
            db_metrics = inspect_inventory_db(db_path, allowed_extensions=adapter.allowed_extensions)

            docs_count = db_metrics.get("documents_count", 0)
            others_count = db_metrics.get("other_resources_count", 0)
            processed_count = docs_count + others_count
            error_count = sum(db_metrics.get("error_counts", {}).values())

            # Si no hay registros en db pero source_map tiene recursos, sumar de source_map
            if db_metrics.get("total_records", 0) == 0 and source_map:
                processed_count = sum(len(ds.resources) for ds in source_map.datasets)
                docs_count = processed_count

            map_json_path = orchestrator.source_output_dir / f"mapa_{adapter.source_id}.json"

            logger.info(
                "Fuente [%s] completada en %.2fs. Documentos reales: %d | Otros recursos: %d | Errores: %d",
                adapter.source_id, elapsed_source, docs_count, others_count, error_count
            )

            results.append({
                "source_id": adapter.source_id,
                "institution": adapter.source_name,
                "base_url": adapter.base_url,
                "config_path": str(cfg_path.relative_to(PROJECT_ROOT) if cfg_path.is_relative_to(PROJECT_ROOT) else cfg_path),
                "adapter_class": adapter.__class__.__name__,
                "adapter_name": adapter.source_name,
                "use_playwright": use_pw,
                "success": True,
                "duration_seconds": elapsed_source,
                "documents_count": docs_count,
                "other_resources_count": others_count,
                "resources_processed": processed_count,
                "resources_error": error_count,
                "meets_criteria": (docs_count >= 1) and (error_count == 0),
                "inventory_db_path": str(db_path.relative_to(PROJECT_ROOT) if db_path.is_relative_to(PROJECT_ROOT) else db_path),
                "map_json_path": str(map_json_path.relative_to(PROJECT_ROOT) if map_json_path.is_relative_to(PROJECT_ROOT) else map_json_path),
                "db_metrics": db_metrics,
            })

        except Exception as exc:
            elapsed_source = time.time() - source_t0
            logger.error("Error fatal ejecutando fuente [%s]: %s", source_id, exc, exc_info=True)
            results.append({
                "source_id": source_id,
                "institution": source_id,
                "config_path": str(cfg_path),
                "success": False,
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
                "duration_seconds": elapsed_source,
                "resources_processed": 0,
                "resources_error": 1,
                "use_playwright": False,
            })

    total_batch_duration = time.time() - t_batch_0
    batch_finish = datetime.now(timezone.utc)
    batch_finish_iso = batch_finish.isoformat()

    batch_meta = {
        "started_at": batch_start_iso,
        "finished_at": batch_finish_iso,
        "total_duration_seconds": total_batch_duration,
        "log_file_relative": str(log_path.relative_to(PROJECT_ROOT) if log_path.is_relative_to(PROJECT_ROOT) else log_path),
    }

    # 3. Generar Reporte Markdown
    report_md_path = reporte_dir / f"reporte_lote_{timestamp_str}.md"
    report_text = generate_markdown_report(batch_meta, results, report_md_path)
    logger.info("Reporte Markdown generado en: %s", report_md_path)

    # 4. Generar Reporte JSON si solicitado
    if args.json:
        report_json_path = reporte_dir / f"reporte_lote_{timestamp_str}.json"
        report_data = {
            "meta": batch_meta,
            "results": results,
        }
        report_json_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Reporte JSON generado en: %s", report_json_path)

    # 5. Resumen final en consola
    logger.info("================================================================================")
    logger.info("Resumen de Ejecución del Lote")
    logger.info("================================================================================")
    for r in results:
        status_tag = "OK" if r.get("success") else "FALLO"
        crit_tag = "CUMPLE" if r.get("meets_criteria") else "NO_CUMPLE"
        logger.info(
            "  [%s|%s] %-15s | %4d docs | %4d otros | %2d err | %6.2fs",
            status_tag, crit_tag, r.get("source_id"), r.get("documents_count", 0),
            r.get("other_resources_count", 0), r.get("resources_error", 0),
            r.get("duration_seconds", 0.0)
        )
    logger.info("Duración total: %.2fs (%.2f min)", total_batch_duration, total_batch_duration / 60)
    logger.info("Reporte completo: %s", report_md_path)


if __name__ == "__main__":
    main()
