"""
Comando CLI para ejecutar la escalera de recuperación de períodos faltantes (B-54).
Evalúa los datasets con huecos detectados en B-53 y aplica la escalera de 4 escalones:
  Escalón 1: Misma URL conocida anteriormente
  Escalón 2: Plantilla de serie temporal (D-17 + HEAD)
  Escalón 3: Rutas alternas dentro del mismo dominio (variaciones y sitemaps)
  Escalón 4: Archivo histórico de la web (Wayback Machine)

Uso:
    python scripts/recuperar_periodos.py
    python scripts/recuperar_periodos.py --sources bcb,ine --max-recoveries 12
    python scripts/recuperar_periodos.py --format json --output output/recuperaciones_b54.json
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List

from crawler.core.recovery_ladder import RecoveryLadder, RecoveredPeriod


def print_table_report(recovered: List[RecoveredPeriod], elapsed_sec: float):
    print("=" * 135)
    print(f"REPORTE DE ESCALERA DE RECUPERACIÓN DE PERÍODOS FALTANTES (B-54) -- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 135)

    if not recovered:
        print("No se recuperaron períodos faltantes con los criterios especificados.")
        print("=" * 135)
        return

    header = f"{'Portal':<6} {'Dataset ID':<22} {'Período':<10} {'Escalón':<25} {'Tamaño (bytes)':<15} {'SHA-256 (primeros 16)':<22} {'URL'}"
    print(header)
    print("-" * 135)

    rung_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    rung_names = {
        1: "1 · Misma URL",
        2: "2 · Plantilla serie",
        3: "3 · Ruta alterna dominio",
        4: "4 · Archivo histórico",
    }
    total_bytes = 0

    for item in recovered:
        r_num = item.recovery_rung
        rung_counts[r_num] = rung_counts.get(r_num, 0) + 1
        total_bytes += item.file_size_bytes

        r_label = f"{r_num} ({item.rung_name})"
        sha_short = item.content_sha256[:16] + "..." if item.content_sha256 else "-"
        url_short = item.url if len(item.url) <= 50 else (item.url[:47] + "...")

        print(
            f"{item.portal.upper():<6} "
            f"{item.dataset_id:<22} "
            f"{item.period:<10} "
            f"{r_label:<25} "
            f"{item.file_size_bytes:<15} "
            f"{sha_short:<22} "
            f"{url_short}"
        )

    print("-" * 135)
    print(f"RESUMEN AGREGADO DE RECUPERACIÓN (Tiempo total: {elapsed_sec:.2f}s):")
    print(f"  Total períodos recuperados y verificados: {len(recovered)}")
    print(f"  Total bytes verificados                 : {total_bytes:,} bytes")
    print("  Distribución por escalón:")
    for r_num in sorted(rung_counts.keys()):
        c = rung_counts[r_num]
        pct = (c / len(recovered) * 100) if recovered else 0
        print(f"    - Escalón {r_num} ({rung_names.get(r_num, 'Otro'):<23}): {c:2d} ({pct:5.1f}%)")
    print("=" * 135)


def main():
    # Asegurar codificación utf-8 en Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Escalera de recuperación de períodos faltantes (B-54)")
    parser.add_argument(
        "--sources",
        default="bcb,ine,asfi",
        help="Fuentes a procesar separadas por coma (ej. bcb,ine,asfi)",
    )
    parser.add_argument(
        "--max-recoveries",
        type=int,
        default=12,
        help="Límite máximo de recuperaciones a ejecutar",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Formato de salida en consola (table o json)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Ruta de archivo JSON donde guardar el resultado detallado",
    )

    args = parser.parse_args()
    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]

    ladder = RecoveryLadder()
    t0 = time.time()
    recovered = ladder.recover_missing_periods(sources=sources, max_recoveries=args.max_recoveries)
    elapsed = time.time() - t0

    if args.format == "table":
        print_table_report(recovered, elapsed)
    else:
        out_dict = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": elapsed,
            "total_recovered": len(recovered),
            "recoveries": [r.to_dict() for r in recovered],
        }
        print(json.dumps(out_dict, indent=2, ensure_ascii=False))

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_dict = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": elapsed,
            "total_recovered": len(recovered),
            "recoveries": [r.to_dict() for r in recovered],
        }
        out_path.write_text(json.dumps(out_dict, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nReporte guardado exitosamente en: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
