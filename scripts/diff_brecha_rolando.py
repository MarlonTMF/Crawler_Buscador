#!/usr/bin/env python3
"""
scripts/diff_brecha_rolando.py
==============================
Herramienta analítica de Fase 3 (B-41) para calcular el diff granular de URLs y hashes
entre los resultados de Rolando (Elecciones De Crawler por URL/Rolando/extracted/output)
y nuestro inventario oficial (output/<portal>/inventory.db).

Identifica exactamente qué URLs y recursos descubrió Rolando que nuestro crawler aún no tiene,
clasificando por patrones de ruta, extensiones y fuentes.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List, Set, Tuple
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("diff_brecha_rolando")

# Mapeo oficial de portales contra los archivos de Rolando
PORTALES_ROLANDO_MAP: Dict[str, List[str]] = {
    "asfi": ["asfi.json", "asfi_bcb.json", "asfi_finrural.json", "asfi_valores.json"],
    "bcb": ["bcb.json"],
    "asofin": ["asofin.json"],
    "ibch": ["ibch.json"],
    "mefp": ["mefp.json"],
    "finrural": ["finrural_indicadores.json"],
    "senamhi": ["senamhi.json"],
    "ae": ["aetn.json"],
    "fam": ["fam.json"],
    "mmym": ["mmym.json"],
    "anapo": ["anapo.json"],
    "cndc": ["cndc.json"],
    "att": ["att.json"],
    "atc": ["atc.json"],
    "ibce_cao": ["ibce.json"],
    "cadexco": ["cadexco.json"],
    "ada": ["ada.json"],
    "ine": ["ine.json"],
    "aps": ["aps.json", "aps_soat.json"],
    "dgac": ["dgac.json"],
    "seprec": ["seprec.json"],
    "snis": ["snis.json"],
}

DOCUMENT_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".csv", ".zip", ".ods", ".xlsm")


def extraer_recursos_rolando(json_path: Path) -> List[Dict[str, Any]]:
    """Extrae recursivamente todos los objetos de recurso descubiertos por Rolando."""
    if not json_path.exists():
        return []

    with open(json_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            logger.warning(f"Error decodificando {json_path}: {e}")
            return []

    recursos: List[Dict[str, Any]] = []

    def walk(obj: Any, context: str = ""):
        if isinstance(obj, dict):
            if "url_descarga" in obj and isinstance(obj["url_descarga"], str):
                item = dict(obj)
                item["_context"] = context
                item["_source_file"] = json_path.name
                recursos.append(item)
            for k, v in obj.items():
                new_ctx = f"{context}/{k}" if context else k
                walk(v, new_ctx)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                walk(item, f"{context}[{i}]")

    walk(data)
    return recursos


def cargar_urls_nuestro_inventario(db_path: Path) -> Dict[str, Dict[str, Any]]:
    """Carga todas las URLs y metadatos de nuestro inventory.db para un portal."""
    if not db_path.exists():
        return {}

    urls: Dict[str, Dict[str, Any]] = {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='resource_audit_log'")
        if not cur.fetchone():
            conn.close()
            return {}

        cur.execute("""
            SELECT canonical_url, status, file_size_bytes, content_sha256
            FROM resource_audit_log
            WHERE status IN ('PROCESADO_EXITOSAMENTE', 'RECUPERADO_VIA_CONTINGENCIA')
        """)
        for r in cur.fetchall():
            urls[r[0].strip()] = {
                "canonical_url": r[0].strip(),
                "status": r[1],
                "file_size_bytes": r[2],
                "content_sha256": r[3],
            }
        conn.close()
    except Exception as e:
        logger.warning(f"Error consultando DB {db_path}: {e}")
    return urls


def normalizar_url_comparacion(url: str) -> str:
    """Normalización suave para comparación de URLs (minúsculas de esquema/host, strips)."""
    u = url.strip()
    parsed = urlparse(u)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path
    query = parsed.query
    reconstructed = f"{scheme}://{netloc}{path}"
    if query:
        reconstructed += f"?{query}"
    return reconstructed


def analizar_portal(
    portal: str,
    rolando_dir: Path,
    output_dir: Path,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Genera el análisis comparativo granular para un portal específico."""
    archivos_rolando = PORTALES_ROLANDO_MAP.get(portal, [f"{portal}.json"])
    recursos_rolando_raw: List[Dict[str, Any]] = []

    for af in archivos_rolando:
        recursos_rolando_raw.extend(extraer_recursos_rolando(rolando_dir / af))

    db_path = output_dir / portal / "inventory.db"
    nuestros_recursos = cargar_urls_nuestro_inventario(db_path)

    # Conjuntos de URLs normalizadas
    rolando_urls_map: Dict[str, Dict[str, Any]] = {}
    for r in recursos_rolando_raw:
        u_raw = r.get("url_descarga", "")
        if u_raw:
            norm = normalizar_url_comparacion(u_raw)
            if norm not in rolando_urls_map:
                rolando_urls_map[norm] = r

    nuestras_urls_norm = {normalizar_url_comparacion(u): v for u, v in nuestros_recursos.items()}

    r_set = set(rolando_urls_map.keys())
    o_set = set(nuestras_urls_norm.keys())

    comunes = r_set & o_set
    solo_rolando = r_set - o_set
    solo_nuestro = o_set - r_set

    # Agrupar solo_rolando por extensiones
    ext_dist: Dict[str, int] = {}
    for u in solo_rolando:
        path = urlparse(u).path.lower()
        ext = Path(path).suffix
        if not ext:
            ext = "(sin_extension)"
        ext_dist[ext] = ext_dist.get(ext, 0) + 1

    # Agrupar solo_rolando por dominios / prefijos de ruta
    prefix_dist: Dict[str, int] = {}
    for u in solo_rolando:
        parsed = urlparse(u)
        path_parts = [p for p in parsed.path.split("/") if p]
        prefix = f"{parsed.netloc}/" + ("/".join(path_parts[:2]) if len(path_parts) >= 2 else (path_parts[0] if path_parts else ""))
        prefix_dist[prefix] = prefix_dist.get(prefix, 0) + 1

    return {
        "portal": portal,
        "rolando_total": len(r_set),
        "nuestro_total": len(o_set),
        "comunes": len(comunes),
        "solo_rolando": len(solo_rolando),
        "solo_nuestro": len(solo_nuestro),
        "solo_rolando_ext": ext_dist,
        "solo_rolando_prefixes": sorted(prefix_dist.items(), key=lambda x: x[1], reverse=True)[:5],
        "ejemplos_solo_rolando": sorted(list(solo_rolando))[:10],
    }


def main():
    parser = argparse.ArgumentParser(description="Diff de brechas contra Rolando")
    parser.add_argument("--portal", "-p", help="Portal específico a analizar (ej. asfi, bcb, asofin, mefp, ibch)")
    parser.add_argument("--rolando-dir", default="Elecciones De Crawler por URL/Rolando/extracted/output", help="Ruta a output de Rolando")
    parser.add_argument("--output-dir", default="output", help="Ruta al output de nuestro crawler")
    parser.add_argument("--export-diff", help="Ruta de archivo JSON donde guardar el diff de URLs faltantes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Mostrar más detalles")

    args = parser.parse_args()

    rolando_dir = Path(args.rolando_dir)
    output_dir = Path(args.output_dir)

    if not rolando_dir.exists():
        logger.error(f"No existe el directorio de Rolando: {rolando_dir}")
        sys.exit(1)

    portales = [args.portal] if args.portal else ["asfi", "bcb", "asofin", "ibch", "mefp", "finrural"]

    print("=" * 85)
    print(f"{'PORTAL':<12} | {'ROLANDO':<8} | {'NUESTRO':<8} | {'COMUNES':<8} | {'SOLO ROL':<10} | {'SOLO NUE':<10} | {'ESTADO'}")
    print("-" * 85)

    resultados = []
    for p in portales:
        res = analizar_portal(p, rolando_dir, output_dir, verbose=args.verbose)
        resultados.append(res)
        
        diff = res["nuestro_total"] - res["rolando_total"]
        if diff > 0:
            estado = f"GANADO (+{diff})"
        elif diff == 0:
            estado = "EMPATADO"
        else:
            estado = f"PERDIDO ({diff})"

        print(f"{p:<12} | {res['rolando_total']:<8} | {res['nuestro_total']:<8} | {res['comunes']:<8} | {res['solo_rolando']:<10} | {res['solo_nuestro']:<10} | {estado}")

    print("=" * 85)

    for res in resultados:
        if res["solo_rolando"] > 0:
            print(f"\n--- Detalle de URLs Faltantes en {res['portal'].upper()} ({res['solo_rolando']} faltantes) ---")
            print("Extensiones:", res["solo_rolando_ext"])
            print("Prefijos principales:")
            for pref, c in res["solo_rolando_prefixes"]:
                print(f"  {pref}: {c} URLs")
            print("Muestra de URLs de Rolando no capturadas por nosotros:")
            for sample in res["ejemplos_solo_rolando"][:5]:
                print(f"  - {sample}")

    if args.export_diff:
        with open(args.export_diff, "w", encoding="utf-8") as f:
            json.dump(resultados, f, indent=2, ensure_ascii=False)
        print(f"\nResultados exportados a {args.export_diff}")


if __name__ == "__main__":
    main()
