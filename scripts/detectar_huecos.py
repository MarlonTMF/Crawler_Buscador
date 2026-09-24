"""
Comando de detección de huecos y atrasos por dataset (B-53).
Genera reporte de períodos esperados vs observados, huecos intermedios y estado
para ASFI, BCB e INE.

Uso:
    python scripts/detectar_huecos.py
    python scripts/detectar_huecos.py --sources bcb --format json
    python scripts/detectar_huecos.py --ref-date 2026-09-24
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List

from crawler.core.gap_detector import GapDetector, DatasetGapReport
from crawler.sources.generic_adapter import GenericSourceAdapter


def run_gap_detection(
    sources: List[str],
    output_base: Path = Path("output"),
    config_base: Path = Path("config"),
    ref_date: date = date.today(),
) -> Dict[str, List[DatasetGapReport]]:
    results: Dict[str, List[DatasetGapReport]] = {}

    for src in sources:
        db_path = output_base / src / "inventory.db"
        cfg_path = config_base / f"source_{src}.yaml"

        if not db_path.exists():
            print(f"[{src.upper()}] No se encontró la base de datos {db_path}", file=sys.stderr)
            continue
        if not cfg_path.exists():
            print(f"[{src.upper()}] No se encontró la configuración {cfg_path}", file=sys.stderr)
            continue

        adapter = GenericSourceAdapter(cfg_path)
        detector = GapDetector(db_path=db_path, reference_date=ref_date)

        src_reports = []
        for rule in adapter.dataset_rules:
            ds_id = rule.get("id")
            periodicity = rule.get("periodicity", "anual")
            tolerance = rule.get("tolerance", 1)

            rep = detector.evaluate_dataset(
                dataset_id=ds_id,
                periodicity=periodicity,
                tolerance=tolerance,
            )
            src_reports.append(rep)

        detector.close()
        results[src] = src_reports

    return results


def print_table_report(results: Dict[str, List[DatasetGapReport]], ref_date: date):
    print("=" * 115)
    print(f"REPORTE DE CALENDARIO, HUECOS Y ATRASOS POR DATASET (B-53) -- Fecha de corte: {ref_date}")
    print("=" * 115)

    total_datasets = 0
    state_counts = {"AL_DIA": 0, "CON_HUECOS": 0, "ATRASADO": 0, "INACTIVO": 0}

    for src, reports in results.items():
        print(f"\n--- PORTAL: {src.upper()} ({len(reports)} datasets) ---")
        header = f"{'Dataset ID':<32} {'Per.':<10} {'Tol':<4} {'Observado':<18} {'Huecos':<8} {'Atraso':<8} {'Estado':<12}"
        print(header)
        print("-" * 115)

        for rep in reports:
            total_datasets += 1
            state_counts[rep.state.value] = state_counts.get(rep.state.value, 0) + 1

            range_str = f"{rep.first_observed_period or '-'}..{rep.last_observed_period or '-'}"
            gaps_str = str(len(rep.intermediate_gaps))
            delay_str = str(rep.delay_periods)

            print(
                f"{rep.dataset_id:<32} "
                f"{rep.periodicity:<10} "
                f"{rep.tolerance:<4} "
                f"{range_str:<18} "
                f"{gaps_str:<8} "
                f"{delay_str:<8} "
                f"{rep.state.value:<12}"
            )
            if rep.intermediate_gaps:
                sample_gaps = ", ".join(rep.intermediate_gaps[:6])
                if len(rep.intermediate_gaps) > 6:
                    sample_gaps += f"... (+{len(rep.intermediate_gaps) - 6} mas)"
                print(f"   |--> Huecos intermedios: [{sample_gaps}]")

    print("\n" + "=" * 115)
    print(f"RESUMEN AGREGADO: {total_datasets} datasets evaluados")
    for st, c in sorted(state_counts.items()):
        pct = (c / total_datasets * 100) if total_datasets > 0 else 0
        print(f"  - {st:<12}: {c:2d} ({pct:5.1f}%)")
    print("=" * 115)


def main():
    parser = argparse.ArgumentParser(description="Detector de huecos y atrasos por dataset (B-53)")
    parser.add_argument(
        "--sources",
        default="asfi,bcb,ine",
        help="Fuentes a evaluar separadas por coma (ej. asfi,bcb,ine)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Formato de salida (table o json)",
    )
    parser.add_argument(
        "--ref-date",
        default=None,
        help="Fecha de referencia para calcular atraso en formato YYYY-MM-DD (default: hoy)",
    )
    args = parser.parse_args()

    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    ref_date = date.fromisoformat(args.ref_date) if args.ref_date else date.today()

    results = run_gap_detection(sources=sources, ref_date=ref_date)

    if args.format == "json":
        json_output = {
            "reference_date": ref_date.isoformat(),
            "sources": {
                src: [r.to_dict() for r in reps]
                for src, reps in results.items()
            }
        }
        print(json.dumps(json_output, indent=2, ensure_ascii=False))
    else:
        print_table_report(results, ref_date=ref_date)


if __name__ == "__main__":
    main()
