from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from crawler.core.validation_engine import build_validation_summary, load_json_records


def _print_summary(summary: Dict[str, Any]) -> None:
    print("\n=== RESUMEN DE VALIDACIÓN DEL CRAWLER ===")
    print(f"Total de registros: {summary['total_records']}")
    print(f"Casos exitosos: {summary['positive_cases']}")
    print(f"Tasa de éxito: {summary['success_rate']:.2%}")
    print(f"Estado: {summary['status']}")
    print(f"Delta vs baseline: {summary['baseline_delta']}")
    print("\nDistribución por score:")
    for score, count in summary["score_distribution"].items():
        print(f"  Score {score}: {count} registros")

    print("\nDebilidades observadas:")
    if summary["weaknesses"]:
        for w in summary["weaknesses"]:
            print(f"  - {w}")
    else:
        print("  - Ninguna debilidad dominante detectada")


def validate_dataset(json_path: str | os.PathLike[str], baseline_path: str | os.PathLike[str] | None = None) -> Dict[str, Any]:
    records = load_json_records(json_path)
    baseline_rows = 0
    if baseline_path:
        base_records = load_json_records(baseline_path)
        baseline_rows = len(base_records)
    summary = build_validation_summary(records, baseline_rows=baseline_rows)
    _print_summary(summary)
    return summary


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    default_json = base_dir / "output" / "excel_urls_diagnostic.json"
    default_baseline = base_dir / "resultadosPrimerCrawleoUnido.xlsx"

    print("=== Validador Profesional del Crawler ===")
    print("1. Validar archivo JSON actual")
    print("2. Validar archivo JSON actual comparando con Excel base")
    print("3. Salir")

    while True:
        choice = input("\nSeleccione una opción [1-3]: ").strip()
        if choice == "1":
            validate_dataset(default_json)
            break
        if choice == "2":
            validate_dataset(default_json, default_baseline)
            break
        if choice == "3":
            print("Saliendo...")
            break
        print("Opción inválida. Intente de nuevo.")


if __name__ == "__main__":
    main()
