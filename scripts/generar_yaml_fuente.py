#!/usr/bin/env python3
"""
scripts/generar_yaml_fuente.py — Generador de esqueletos YAML para fuentes del prospector externo.

Deriva automáticamente la configuración estructural de una fuente a partir de
`output/excel_urls_diagnostic.json` (Track A) y emite un archivo `config/source_<id>.yaml`.

REGLA DE DISEÑO CRÍTICA (Etapa C / B-12):
- Las reglas de clasificación (`classification.dataset_rules`, `classification.excluded_path_keywords`)
  se generan VACÍAS con un comentario `# TODO: completar tras explorar el sitio`.
  NUNCA inventar patrones o palabras clave plausibles (/informes/, /estadisticas/, etc.),
  ya que un YAML autogenerado con reglas supuestas corre sin error y no encuentra nada
  (fallo silencioso).
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import yaml

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("generar_yaml_fuente")


def clean_source_id(fuente: str) -> str:
    """Normaliza el identificador de la fuente para usarlo como id y nombre de archivo."""
    s = fuente.strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = s.strip("_")
    return s


def derive_domains(url: str) -> List[str]:
    """Deriva la lista de dominios permitidos a partir de una URL."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if ":" in netloc:
        netloc = netloc.split(":")[0]
    if not netloc:
        return []

    domains: List[str] = []
    if netloc.startswith("www."):
        domains.append(netloc)
        domains.append(netloc[4:])
    else:
        domains.append(f"www.{netloc}")
        domains.append(netloc)
    return domains


def derive_base_url(url: str) -> str:
    """Extrae el scheme y netloc base de una URL."""
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc
    return f"{scheme}://{netloc}"


def find_source_record(fuente_query: str, diagnostic_path: Path) -> Optional[Dict[str, Any]]:
    """Busca un registro en el diagnóstico por nombre o id de fuente (case-insensitive)."""
    if not diagnostic_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de diagnóstico en: {diagnostic_path}")

    with open(diagnostic_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    query = fuente_query.strip().lower()
    for row in data:
        f_name = str(row.get("Fuente", "")).strip().lower()
        if f_name == query or clean_source_id(f_name) == query:
            return row

    return None


def is_headless_required(record: Dict[str, Any]) -> bool:
    """Determina si la fuente requiere renderizado con navegador headless (Playwright)."""
    fuente_upper = str(record.get("Fuente", "")).strip().upper()
    if fuente_upper in ("BCP", "BCRP"):
        return True

    status = str(record.get("HTTP_Status", "")).upper()
    if "CLOUDFLARE" in status or "CHALLENGE" in status:
        return True

    error_detail = str(record.get("Error_Detail", "")).lower()
    if "headless" in error_detail or "cloudflare" in error_detail:
        return True

    mapping_note = str(record.get("mapping_note", "")).lower()
    if "headless" in mapping_note or "requiere navegador" in mapping_note:
        return True

    return False


def is_strapi_spa(record: Dict[str, Any]) -> bool:
    """Determina si la fuente es una SPA con backend Strapi/API (ej. SICSANTACRUZ)."""
    fuente_upper = str(record.get("Fuente", "")).strip().upper()
    if fuente_upper == "SICSANTACRUZ":
        return True

    note = (str(record.get("mapping_note", "")) + " " + str(record.get("note", ""))).lower()
    return "api/estudios" in note or "strapi" in note


def build_yaml_skeleton(
    record: Dict[str, Any],
    max_depth: int = 2,
    max_pages: int = 120,
    rate_limit: float = 1.0,
) -> Tuple[str, Dict[str, Any]]:
    """
    Construye el texto YAML formateado con comentarios TODO explícitos.
    Retorna la tupla (yaml_text, parsed_dict).
    """
    fuente = str(record.get("Fuente", "")).strip()
    source_id = clean_source_id(fuente)
    institucion = str(record.get("Institucion") or fuente).strip()
    # Escapar comillas dobles en el nombre institucional
    institucion_escaped = institucion.replace('"', '\\"')

    final_url = record.get("Final_Url") or record.get("Url_Original")
    if not final_url:
        status = record.get("HTTP_Status")
        raise ValueError(
            f"La fuente '{fuente}' no tiene Final_Url válida (HTTP_Status: {status}). "
            "No se puede generar un esqueleto para una fuente excluida o sin URL verificada."
        )

    base_url = derive_base_url(final_url)
    domains = derive_domains(final_url)
    domains_yaml = "\n".join(f"    - {d}" for d in domains)

    headless_needed = is_headless_required(record)
    strapi_needed = is_strapi_spa(record)

    headless_flag_str = "true" if headless_needed else "false"

    # Construcción de semillas y notas operativas
    strapi_comment = ""
    if strapi_needed:
        strapi_comment = (
            "    # NOTA OPERATIVA (Etapa C): El sitio es una SPA con backend Strapi.\n"
            "    # Los documentos no se obtienen raspando HTML; consultar directamente:\n"
            "    # https://ice.santacruz.gob.bo/api/estudios\n"
        )

    headless_comment = ""
    if headless_needed:
        headless_comment = (
            "  # Fuente protegida por Cloudflare/WAF bot detection (D-03).\n"
            "  # Requiere navegador real (Playwright domcontentloaded) para acceder a los datos.\n"
        )

    yaml_text = f"""# ==============================================================================
# Configuración del Prospector Externo — DataX Web Prospector
# Fuente: {fuente} ({institucion})
# Esqueleto autogenerado por scripts/generar_yaml_fuente.py (Etapa C / B-12)
# ==============================================================================

source:
  id: {source_id}
  name: "{institucion_escaped}"
  base_url: {base_url}
  allowed_domains:
{domains_yaml}

crawl:
  seeds:
    - {final_url}
{strapi_comment}{headless_comment}  max_depth: {max_depth}
  max_pages: {max_pages}
  strategy: bfs
  rate_limit_per_second: {rate_limit}
  allowed_extensions: [pdf, xlsx, xls, csv, zip]
  use_sitemaps: true
  use_wayback: false
  use_search_dorking: false
  use_subdomain_enumeration: false
  use_async_fetcher: false
  use_playwright: {headless_flag_str}
  use_playwright_ocr: {headless_flag_str}
  headless: {headless_flag_str}

audit:
  enabled: true

content_hashing:
  enabled: false

monitoring:
  drift_threshold: 0.30
  historical_resource_counts: []

search_dorking:
  provider: none
  max_results: 50

classification:
  document_path_tokens: []
    # TODO: completar tras explorar el sitio (ej. tokens en URL que indican documentos)
  dataset_rules: []
    # TODO: completar tras explorar el sitio (definir grupos logicos de documentos)
  excluded_path_keywords: []
    # TODO: completar tras explorar el sitio (rutas institucionales o no relevantes a omitir)

period_extraction:
  months_es:
    enero: 1
    febrero: 2
    marzo: 3
    abril: 4
    mayo: 5
    junio: 6
    julio: 7
    agosto: 8
    septiembre: 9
    octubre: 10
    noviembre: 11
    diciembre: 12
  filename_pattern: "" # TODO: definir regex con (?P<year>...) segun nomenclatura de archivos de la fuente

canonicalization:
  drop_query_parameters:
    - utm_source
    - utm_medium
    - utm_campaign
    - fbclid
  preserve_query_parameters: []
"""

    # Verificación sintáctica estricta con PyYAML
    try:
        parsed_dict = yaml.safe_load(yaml_text)
    except Exception as e:
        raise RuntimeError(f"Error de sintaxis al validar el YAML generado para '{fuente}': {e}")

    return yaml_text, parsed_dict


def generate_yaml_for_source(
    fuente: str,
    diagnostic_path: Path,
    output_dir: Path,
    force: bool = False,
    stdout: bool = False,
) -> Path:
    """Genera el archivo YAML para una fuente especificada."""
    record = find_source_record(fuente, diagnostic_path)
    if not record:
        raise ValueError(
            f"No se encontró la fuente '{fuente}' en {diagnostic_path}. "
            "Verificá el nombre exacto en el catálogo."
        )

    source_id = clean_source_id(record.get("Fuente", fuente))
    target_path = output_dir / f"source_{source_id}.yaml"

    yaml_text, _ = build_yaml_skeleton(record)

    if stdout:
        sys.stdout.write(yaml_text)
        return target_path

    if target_path.exists() and not force:
        raise FileExistsError(
            f"El archivo {target_path} ya existe. Usá --force para sobreescribirlo "
            "(cuidado: no sobreescribir configuraciones ya calibradas a mano como FINRURAL o BBV)."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(yaml_text)

    logger.info(f"Esqueleto YAML generado exitosamente en: {target_path}")
    return target_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generador de esqueletos YAML para fuentes del crawler (Etapa C / B-12)"
    )
    parser.add_argument(
        "--fuente",
        type=str,
        help="Nombre o sigla de la fuente en el catálogo (ej. FINRURAL, BCP, BCRP, SICSANTACRUZ)",
    )
    parser.add_argument(
        "--diagnostic-file",
        type=Path,
        default=Path("output/excel_urls_diagnostic.json"),
        help="Ruta al archivo maestro de diagnóstico (default: output/excel_urls_diagnostic.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("config"),
        help="Directorio de salida para los archivos YAML (default: config/)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Sobreescribir el archivo de configuración si ya existe",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Imprimir el YAML generado a stdout en lugar de escribir a disco",
    )
    parser.add_argument(
        "--all-accessible",
        action="store_true",
        help="Generar esqueletos para todas las fuentes verificadas y accesibles del catálogo",
    )

    args = parser.parse_args()

    if not args.fuente and not args.all_accessible:
        parser.print_help()
        logger.error("Debes especificar --fuente <nombre> o --all-accessible")
        return 1

    diagnostic_path = args.diagnostic_file
    if not diagnostic_path.exists():
        logger.error(f"Archivo de diagnóstico no encontrado: {diagnostic_path}")
        return 1

    if args.all_accessible:
        with open(diagnostic_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        generated = 0
        skipped = 0
        errors = 0
        for r in data:
            fuente_name = r.get("Fuente")
            if not fuente_name:
                continue
            final_url = r.get("Final_Url") or r.get("Url_Original")
            if not final_url:
                logger.info(f"Omitiendo fuente sin URL operativa: {fuente_name}")
                skipped += 1
                continue

            try:
                generate_yaml_for_source(
                    fuente=fuente_name,
                    diagnostic_path=diagnostic_path,
                    output_dir=args.output_dir,
                    force=args.force,
                    stdout=False,
                )
                generated += 1
            except FileExistsError:
                logger.warning(f"Ya existe YAML para '{fuente_name}', omitiendo (usá --force para reemplazar).")
                skipped += 1
            except Exception as e:
                logger.error(f"Error generando YAML para '{fuente_name}': {e}")
                errors += 1

        logger.info(f"Proceso finalizado: {generated} generados, {skipped} omitidos, {errors} errores.")
        return 0 if errors == 0 else 1

    try:
        generate_yaml_for_source(
            fuente=args.fuente,
            diagnostic_path=diagnostic_path,
            output_dir=args.output_dir,
            force=args.force,
            stdout=args.stdout,
        )
        return 0
    except Exception as e:
        logger.error(f"Error al generar esqueleto: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
