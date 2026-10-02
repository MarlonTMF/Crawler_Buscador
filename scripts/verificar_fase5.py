"""
scripts/verificar_fase5.py
==========================
Script de verificación oficial de la Fase 5: mejora de recuperación de fuentes perdidas.
Imprime los seis indicadores clave de la Sección 1 de docs/plan_bloques_fase5.md:
  1. Resultados falsos admitidos (Meta: 0 — no negociable)
  2. Recuperaciones verificadas (Meta: >= 10)
  3. Estrategias con al menos una recuperación (Meta: >= 3 de 5)
  4. URLs catalogadas revalidadas (Meta: 1.165 de 1.165)
  5. Cobertura de fechas en BCB (Meta: >= 65 %)
  6. Faltantes consultados al agente (Meta: todos los pendientes)

Uso:
    python scripts/verificar_fase5.py
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Dict, List, Set, Tuple
from urllib.parse import unquote, urlparse


TOTAL_CATALOGADAS_TARGET = 1165  # 121 BCB + 443 INE + 601 ASFI


def get_recovery_metrics() -> Dict[str, Any]:
    """Carga los resultados de la corrida de recuperación más reciente y calcula indicadores."""
    candidates = [
        Path("output/recup_fase5.json"),
        Path("output/recup_b66.json"),
        Path("output/recup_b65.json"),
        Path("output/recup_b59.json"),
        Path("output/baseline_test.json"),
        Path("docs/entregas/recuperaciones_b54b.json"),
    ]
    data = None
    source_file = None
    for p in candidates:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                source_file = str(p)
                break
            except Exception:
                continue

    if not data:
        return {
            "source_file": None,
            "false_positives": 0,
            "verified_recoveries": 0,
            "strategies_count": 0,
            "gemini_calls": 0,
            "total_pending": 34,
            "recoveries": [],
            "rechazos_calidad": [],
        }

    recoveries = data.get("recoveries", [])
    rechazos = data.get("rechazos_calidad", [])
    agent_stats = data.get("agent_stats", {})
    gemini_calls = agent_stats.get("faltantes_consultados", data.get("gemini_calls_count", 0))

    # Identificar falsos positivos en las recuperaciones admitidas:
    # 1. Huella SHA-256 repetida en el mismo dataset entre distintos períodos
    # 2. Año de cuatro dígitos en el nombre del archivo contradictorio con el período
    false_positives = 0
    verified = []
    seen_hashes: Dict[Tuple[str, str], Dict[str, str]] = {}

    for item in recoveries:
        portal = item.get("portal", "").lower()
        dataset_id = item.get("dataset_id", "")
        period = str(item.get("period", ""))
        sha256 = item.get("content_sha256", "")
        url = item.get("url", "")
        r_num = item.get("recovery_rung", 0)

        is_fp = False
        fp_reason = None

        # Chequeo 1: Huella repetida
        ds_key = (portal, dataset_id)
        if ds_key not in seen_hashes:
            seen_hashes[ds_key] = {}
        if sha256 and sha256 in seen_hashes[ds_key]:
            prev_p = seen_hashes[ds_key][sha256]
            if prev_p != period:
                is_fp = True
                fp_reason = f"Huella repetida con período {prev_p}"
        elif sha256:
            seen_hashes[ds_key][sha256] = period

        # Chequeo 2: Año contradictorio en el filename
        filename = unquote(urlparse(url).path).split("/")[-1]
        file_years = set(re.findall(r"(?:^|[^\d])(19\d\d|20\d\d)(?:[^\d]|$)", filename))
        period_years = set(re.findall(r"(?:^|[^\d])(19\d\d|20\d\d)(?:[^\d]|$)", period))

        if file_years and period_years and not (file_years & period_years):
            is_fp = True
            fp_reason = f"Año contradictorio en filename ({file_years} != {period_years})"

        if is_fp:
            false_positives += 1
        else:
            verified.append(item)

    strategies = {item.get("recovery_rung") for item in verified if item.get("recovery_rung")}

    return {
        "source_file": source_file,
        "false_positives": false_positives,
        "verified_recoveries": len(verified),
        "strategies_count": len(strategies),
        "gemini_calls": gemini_calls,
        "total_pending": 34,
        "recoveries": recoveries,
        "rechazos_calidad": rechazos,
    }


def get_revalidation_metrics() -> Tuple[int, int]:
    """Obtiene el conteo de URLs catalogadas revalidadas."""
    total_target = TOTAL_CATALOGADAS_TARGET
    total_revalidated = 0

    reval_files = [
        Path("output/revalidacion_resumen.json"),
        Path("output/revalidacion_bcb.json"),
        Path("output/revalidacion_ine.json"),
        Path("output/revalidacion_asfi.json"),
    ]

    seen_keys: Set[str] = set()
    total_from_summary = 0
    for rf in reval_files:
        if rf.exists():
            try:
                data = json.loads(rf.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    urls = data.get("revalidated_urls") or data.get("results") or []
                    src = data.get("source", "")
                    for u in urls:
                        if isinstance(u, str):
                            seen_keys.add(u)
                        elif isinstance(u, dict):
                            k = f"{src}:{u.get('resource_id') or u.get('url')}"
                            seen_keys.add(k)
                    if "total_revalidated" in data:
                        total_from_summary = max(total_from_summary, data["total_revalidated"])
            except Exception:
                pass

    if seen_keys:
        total_revalidated = len(seen_keys)
    elif total_from_summary > 0:
        total_revalidated = total_from_summary

    return total_revalidated, total_target


def get_bcb_date_coverage() -> Tuple[float, int, int]:
    """Calcula la cobertura de fechas en BCB desde inventory.db."""
    db_path = Path("output/bcb/inventory.db")
    if not db_path.exists():
        return 0.0, 0, 0

    try:
        with sqlite3.connect(db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM resource_audit_log")
            total = c.fetchone()[0] or 0
            c.execute(
                "SELECT COUNT(*) FROM resource_audit_log WHERE period_start IS NOT NULL AND length(period_start) > 0"
            )
            with_date = c.fetchone()[0] or 0
            pct = (with_date / total * 100.0) if total > 0 else 0.0
            return pct, with_date, total
    except Exception:
        return 0.0, 0, 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    rec = get_recovery_metrics()
    reval_cur, reval_target = get_revalidation_metrics()
    bcb_pct, bcb_with_date, bcb_total = get_bcb_date_coverage()

    fp = rec["false_positives"]
    vr = rec["verified_recoveries"]
    strat = rec["strategies_count"]
    calls = rec["gemini_calls"]
    pending = rec["total_pending"]

    # Estado de cumplimiento
    c_fp = "SÍ" if fp == 0 else f"NO ({fp} falsos)"
    c_vr = "SÍ" if vr >= 10 else f"EN PROGRESO ({vr}/10)"
    c_strat = "SÍ" if strat >= 3 else f"EN PROGRESO ({strat}/3)"
    c_reval = "SÍ" if reval_cur >= reval_target else f"EN PROGRESO ({reval_cur}/{reval_target})"
    c_bcb = "SÍ" if bcb_pct >= 65.0 else f"EN PROGRESO ({bcb_pct:.1f}%/65%)"
    c_agent = "SÍ" if calls >= pending else f"EN PROGRESO ({calls}/{pending})"

    print("=" * 105)
    print("VERIFICACIÓN DE INDICADORES DE FASE 5 — RECUPERACIÓN DE FUENTES PERDIDAS")
    print("=" * 105)
    if rec["source_file"]:
        print(f"Archivo de corrida evaluado: {rec['source_file']}")
    else:
        print("Archivo de corrida evaluado: Ninguno (sin corrida registrada)")
    print("-" * 105)

    header = f"{'Indicador':<42} {'Línea base':<15} {'Meta':<22} {'Estado actual':<16} {'Cumple'}"
    print(header)
    print("-" * 105)

    row1 = f"{'Resultados falsos admitidos':<42} {'6':<15} {'0 — no negociable':<22} {str(fp):<16} {c_fp}"
    row2 = f"{'Recuperaciones verificadas':<42} {'3':<15} {'≥ 10':<22} {str(vr):<16} {c_vr}"
    row3 = f"{'Estrategias con ≥1 recuperación':<42} {'1 de 5':<15} {'≥ 3 de 5':<22} {f'{strat} de 5':<16} {c_strat}"
    row4 = f"{'URLs catalogadas revalidadas':<42} {'0 de 1.165':<15} {'1.165 de 1.165':<22} {f'{reval_cur} de {reval_target}':<16} {c_reval}"
    row5 = f"{'Cobertura de fechas en BCB':<42} {'32 %':<15} {'≥ 65 %':<22} {f'{bcb_pct:.1f} %':<16} {c_bcb}"
    row6 = f"{'Faltantes consultados al agente':<42} {'~10 de 34':<15} {'todos (≥34)':<22} {f'{calls} de {pending}':<16} {c_agent}"

    print(row1)
    print(row2)
    print(row3)
    print(row4)
    print(row5)
    print(row6)
    print("=" * 105)


if __name__ == "__main__":
    main()
