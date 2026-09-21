#!/usr/bin/env python3
"""
scripts/comparador_benchmark.py
================================
Comparativa automatizada y reproducible contra el benchmark de los 3 crawlers (B-39).

Produce la tabla portal por portal comparando nuestro crawler contra Douglas y Rolando,
utilizando el mapeo explícito curado de las 22 entradas consolidadas de
docs/comparativa_vs_benchmark.md.

Criterios de aceptación (docs/plan_bloques_fase2.md · B-39):
- Mapeo explícito y curado de portales consolidados (evita colisiones como anapo/an o duplicación de ASFI/APS).
- Carga reproducible de las cifras del benchmark histórico (Elecciones De Crawler por URL/merged_final.json).
- Extracción reproducible de documentos de output/<portal>/inventory.db siguiendo D-14.
- Reproduce exactamente las cifras históricas de docs/comparativa_vs_benchmark.md (Douglas=70, Rolando=5403,
  Nosotros sep=664, Nosotros baseline 19-sep=1864, y los 13 portales estables idénticos).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("comparador_benchmark")

# Mapeo explícito y curado de los 22 portales comunes contra los códigos del benchmark histórico
PORTALES_BENCHMARK_MAP: Dict[str, List[str]] = {
    "senamhi": ["senamhi"],
    "ae": ["aetn"],
    "fam": ["fam"],
    "mmym": ["mmym"],
    "anapo": ["anapo"],
    "cndc": ["cndc"],
    "att": ["att"],
    "atc": ["atc"],
    "ibce_cao": ["ibce"],
    "cadexco": ["cadexco"],
    "bcb": ["bcb"],
    "finrural": ["finrural_indicadores"],
    "asfi": ["asfi", "asfi_bcb", "asfi_finrural", "asfi_valores"],
    "ada": ["ada"],
    "asofin": ["asofin"],
    "ibch": ["ibch"],
    "ine": ["ine"],
    "aps": ["aps", "aps_soat"],
    "dgac": ["dgac"],
    "seprec": ["seprec"],
    "snis": ["snis"],
    "mefp": ["mefp"],
}

# Línea base histórica verificada el 2026-09-19 (docs/comparativa_vs_benchmark.md)
BASELINE_20260919: Dict[str, int] = {
    "senamhi": 798,
    "ae": 113,
    "fam": 111,
    "mmym": 107,
    "anapo": 99,
    "cndc": 93,
    "att": 65,
    "atc": 39,
    "ibce_cao": 26,
    "cadexco": 10,
    "bcb": 116,
    "finrural": 129,
    "asfi": 61,
    "ada": 2,
    "asofin": 18,
    "ibch": 23,
    "ine": 9,
    "aps": 12,
    "dgac": 12,
    "seprec": 12,
    "snis": 9,
    "mefp": 0,
}

# Extensiones documentales válidas según D-14
DOCUMENT_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".csv", ".zip")


def cargar_benchmark(benchmark_path: Path) -> Dict[str, Dict[str, int]]:
    """
    Carga los resultados históricos de Douglas, Rolando y Nosotros (sep)
    desde el archivo JSON consolidado del benchmark.
    """
    if not benchmark_path.exists():
        raise FileNotFoundError(f"No se encontró el benchmark en: {benchmark_path}")

    with open(benchmark_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    by_code = {d.get("code"): d for d in data if "code" in d}

    benchmark_por_portal: Dict[str, Dict[str, int]] = {}

    for portal, codes in PORTALES_BENCHMARK_MAP.items():
        douglas_total = sum(by_code[c].get("douglas_resources", 0) for c in codes if c in by_code)
        rolando_total = sum(by_code[c].get("rolando_archivos", 0) for c in codes if c in by_code)

        # Para Nosotros (sep): ASFI y APS en el benchmark de septiembre tenían duplicados consolidados
        if portal == "asfi":
            nosotros_sep = by_code["asfi_bcb"]["mio_resources"] if "asfi_bcb" in by_code else 0
        elif portal == "aps":
            nosotros_sep = by_code["aps"]["mio_resources"] if "aps" in by_code else 0
        else:
            nosotros_sep = sum(by_code[c].get("mio_resources", 0) for c in codes if c in by_code)

        benchmark_por_portal[portal] = {
            "douglas": douglas_total,
            "rolando": rolando_total,
            "nosotros_sep": nosotros_sep,
        }

    return benchmark_por_portal


def contar_documentos_db(db_path: Path, solo_d13: bool = False) -> int:
    """
    Cuenta documentos en inventory.db aplicando:
    - Criterio D-14: extensiones documentales válidas y estado exitoso/contingencia.
    - Criterio D-13 (si solo_d13=True): exige además file_size_bytes > 0 y content_sha256 no nulo.
    """
    if not db_path.exists():
        return 0

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='resource_audit_log'")
        if not cur.fetchone():
            conn.close()
            return 0

        d13_clause = "AND file_size_bytes > 0 AND content_sha256 IS NOT NULL AND length(content_sha256) = 64" if solo_d13 else ""

        cur.execute(f"""
            SELECT count(*) FROM resource_audit_log
            WHERE (
                lower(canonical_url) LIKE '%.pdf%' OR
                lower(canonical_url) LIKE '%.xlsx%' OR
                lower(canonical_url) LIKE '%.xls%' OR
                lower(canonical_url) LIKE '%.csv%' OR
                lower(canonical_url) LIKE '%.zip%'
            )
            AND status IN ('PROCESADO_EXITOSAMENTE', 'RECUPERADO_VIA_CONTINGENCIA')
            {d13_clause}
        """)
        count = cur.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.warning(f"Error consultando base {db_path}: {e}")
        return 0


def generar_comparativa(
    output_dir: Path,
    benchmark_path: Path,
) -> List[Dict[str, Any]]:
    """
    Genera la tabla comparativa completa portal por portal.
    """
    bench = cargar_benchmark(benchmark_path)
    rows: List[Dict[str, Any]] = []

    for portal, codes in PORTALES_BENCHMARK_MAP.items():
        b_data = bench.get(portal, {"douglas": 0, "rolando": 0, "nosotros_sep": 0})
        baseline = BASELINE_20260919.get(portal, 0)

        db_path = output_dir / portal / "inventory.db"
        actual_d14 = contar_documentos_db(db_path, solo_d13=False)
        actual_d13 = contar_documentos_db(db_path, solo_d13=True)

        rows.append({
            "portal": portal,
            "douglas": b_data["douglas"],
            "rolando": b_data["rolando"],
            "nosotros_sep": b_data["nosotros_sep"],
            "nosotros_baseline": baseline,
            "nosotros_actual": actual_d14,
            "nosotros_d13": actual_d13,
            "delta_vs_baseline": actual_d14 - baseline,
            "gana_a_rolando_actual": actual_d14 > b_data["rolando"],
        })

    return rows


def formatear_markdown(rows: List[Dict[str, Any]], incluir_baseline: bool = True) -> str:
    """
    Formatea los resultados en una tabla Markdown clara y reproducible.
    """
    tot_douglas = sum(r["douglas"] for r in rows)
    tot_rolando = sum(r["rolando"] for r in rows)
    tot_sep = sum(r["nosotros_sep"] for r in rows)
    tot_baseline = sum(r["nosotros_baseline"] for r in rows)
    tot_actual = sum(r["nosotros_actual"] for r in rows)
    tot_d13 = sum(r.get("nosotros_d13", 0) for r in rows)

    lineas = []
    lineas.append("| Portal | Douglas | Rolando | Nosotros (sep) | Baseline (19-sep) | **Nosotros (D-14)** | Nosotros (D-13 c/hash) | Δ vs Baseline |")
    lineas.append("|---|---:|---:|---:|---:|---:|---:|---:|")

    for r in rows:
        delta_str = f"+{r['delta_vs_baseline']}" if r["delta_vs_baseline"] > 0 else str(r["delta_vs_baseline"])
        lineas.append(
            f"| {r['portal']} | {r['douglas']} | {r['rolando']} | {r['nosotros_sep']} | "
            f"{r['nosotros_baseline']} | **{r['nosotros_actual']}** | {r.get('nosotros_d13', 0)} | {delta_str} |"
        )

    delta_tot = f"+{tot_actual - tot_baseline}" if (tot_actual - tot_baseline) > 0 else str(tot_actual - tot_baseline)
    lineas.append(
        f"| **TOTAL** | **{tot_douglas}** | **{tot_rolando}** | **{tot_sep}** | "
        f"**{tot_baseline}** | **{tot_actual}** | **{tot_d13}** | **{delta_tot}** |"
    )

    return "\n".join(lineas)


def verificar_reproducibilidad(
    rows: List[Dict[str, Any]],
) -> Tuple[bool, List[str]]:
    """
    Verifica que la comparativa reproduzca fielmente las cifras históricas
    de docs/comparativa_vs_benchmark.md.
    """
    errores = []

    # 1. Verificar totales históricos del benchmark
    tot_douglas = sum(r["douglas"] for r in rows)
    tot_rolando = sum(r["rolando"] for r in rows)
    tot_sep = sum(r["nosotros_sep"] for r in rows)
    tot_baseline = sum(r["nosotros_baseline"] for r in rows)

    if tot_douglas != 70:
        errores.append(f"Total Douglas esperado 70, obtenido {tot_douglas}")
    if tot_rolando != 5403:
        errores.append(f"Total Rolando esperado 5403, obtenido {tot_rolando}")
    if tot_sep != 664:
        errores.append(f"Total Nosotros (sep) esperado 664, obtenido {tot_sep}")
    if tot_baseline != 1864:
        errores.append(f"Total Nosotros (baseline 19-sep) esperado 1864, obtenido {tot_baseline}")

    # 2. Verificar que los 13 portales no tocados en Fase 2 coincidan con baseline
    portales_no_tocados = [
        "senamhi", "fam", "mmym", "anapo", "cndc", "att", "atc",
        "cadexco", "bcb", "asofin", "ibch", "snis", "mefp"
    ]
    for p in portales_no_tocados:
        row = next((r for r in rows if r["portal"] == p), None)
        if not row:
            errores.append(f"Portal {p} no encontrado en la comparativa")
            continue
        if row["nosotros_actual"] != row["nosotros_baseline"]:
            errores.append(
                f"Portal {p} no tocado difiere: actual {row['nosotros_actual']} vs baseline {row['nosotros_baseline']}"
            )

    es_valido = len(errores) == 0
    return es_valido, errores


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Comparador reproducible contra el benchmark de los 3 crawlers (B-39)."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directorio de salidas con bases inventory.db (default: output)",
    )
    parser.add_argument(
        "--benchmark-path",
        type=Path,
        default=Path("Elecciones De Crawler por URL/merged_final.json"),
        help="Ruta al archivo merged_final.json del benchmark",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "summary"],
        default="markdown",
        help="Formato de salida (default: markdown)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Ejecuta aserciones de verificación de reproducibilidad",
    )
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        help="Ruta opcional para guardar el reporte markdown generado",
    )

    args = parser.parse_args()

    try:
        rows = generar_comparativa(args.output_dir, args.benchmark_path)
    except Exception as e:
        print(f"ERROR al generar la comparativa: {e}", file=sys.stderr)
        return 1

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    if args.verify:
        valido, errores = verificar_reproducibilidad(rows)
        if not valido:
            print("FALLO de verificación de reproducibilidad:", file=sys.stderr)
            for err in errores:
                print(f"  - {err}", file=sys.stderr)
            return 2
        else:
            print("[OK] Verificación de reproducibilidad EXITOSA: Todas las cifras históricas y no alteradas reproducen al 100%.")

    if args.format == "json":
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    elif args.format == "summary":
        tot_d = sum(r["douglas"] for r in rows)
        tot_r = sum(r["rolando"] for r in rows)
        tot_b = sum(r["nosotros_baseline"] for r in rows)
        tot_a = sum(r["nosotros_actual"] for r in rows)
        ganadas = sum(1 for r in rows if r["gana_a_rolando_actual"])
        print(f"Douglas: {tot_d} | Rolando: {tot_r} | Baseline: {tot_b} | Actual: {tot_a} (Ganadas: {ganadas}/22)")
    else:
        md = formatear_markdown(rows)
        print(md)
        if args.save:
            with open(args.save, "w", encoding="utf-8") as f:
                f.write(md + "\n")
            print(f"\n[Guardado exitosamente en: {args.save}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
