"""
scripts/revalidar_urls.py
=========================
Script CLI para revalidar las URLs catalogadas en resource_audit_log (B-60 / P-1).

Ejecuta solicitudes HEAD (con GET de respaldo) sobre los 1.165 recursos catalogados
de BCB, INE y ASFI para detectar documentos movidos, eliminados o vigentes.

Uso:
    python scripts/revalidar_urls.py --sources bcb,ine,asfi --format resumen
    python scripts/revalidar_urls.py --sources bcb --format table
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Dict, List

from crawler.core.url_revalidator import UrlRevalidator, UrlRevalidationResult


def print_resumen_table(all_summaries: Dict[str, Dict[str, int]], elapsed_sec: float):
    print("=" * 105)
    print(f"REPORTE DE REVALIDACIÓN DE URLs CATALOGADAS (B-60) -- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 105)

    header = f"{'Fuente':<10} {'Total URLs':<12} {'VIGENTE':<18} {'REDIRIGIDA':<18} {'ELIMINADA':<18} {'INACCESIBLE':<18}"
    print(header)
    print("-" * 105)

    grand_total = 0
    tot_vigente = 0
    tot_redirigida = 0
    tot_eliminada = 0
    tot_inaccesible = 0

    for source, summary in all_summaries.items():
        total = summary.get("total_urls", 0)
        v = summary.get("VIGENTE", 0)
        r = summary.get("REDIRIGIDA", 0)
        e = summary.get("ELIMINADA", 0)
        i = summary.get("INACCESIBLE", 0)

        grand_total += total
        tot_vigente += v
        tot_redirigida += r
        tot_eliminada += e
        tot_inaccesible += i

        v_pct = (v / total * 100) if total else 0.0
        r_pct = (r / total * 100) if total else 0.0
        e_pct = (e / total * 100) if total else 0.0
        i_pct = (i / total * 100) if total else 0.0

        v_str = f"{v} ({v_pct:.1f}%)"
        r_str = f"{r} ({r_pct:.1f}%)"
        e_str = f"{e} ({e_pct:.1f}%)"
        i_str = f"{i} ({i_pct:.1f}%)"

        print(f"{source.upper():<10} {total:<12} {v_str:<18} {r_str:<18} {e_str:<18} {i_str:<18}")

    print("-" * 105)
    gv_pct = (tot_vigente / grand_total * 100) if grand_total else 0.0
    gr_pct = (tot_redirigida / grand_total * 100) if grand_total else 0.0
    ge_pct = (tot_eliminada / grand_total * 100) if grand_total else 0.0
    gi_pct = (tot_inaccesible / grand_total * 100) if grand_total else 0.0

    print(
        f"{'TOTAL':<10} {grand_total:<12} "
        f"{f'{tot_vigente} ({gv_pct:.1f}%)':<18} "
        f"{f'{tot_redirigida} ({gr_pct:.1f}%)':<18} "
        f"{f'{tot_eliminada} ({ge_pct:.1f}%)':<18} "
        f"{f'{tot_inaccesible} ({gi_pct:.1f}%)':<18}"
    )
    print("=" * 105)
    print(f"Tiempo total: {elapsed_sec:.1f} s · Revalidación completada exitosamente.")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Revalidador de URLs catalogadas (B-60)")
    parser.add_argument(
        "--sources",
        default="bcb,ine,asfi",
        help="Fuentes a revalidar separadas por coma (ej. bcb,ine,asfi)",
    )
    parser.add_argument(
        "--format",
        choices=["resumen", "json", "tabla"],
        default="resumen",
        help="Formato de salida (resumen, json, tabla)",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=None,
        help="Sobrescribir la tasa de peticiones por segundo",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Tiempo de espera por petición HTTP en segundos",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Directorio de salida para los archivos JSON de revalidación",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Forzar revalidación completa ignorando resultados previos existentes",
    )

    args = parser.parse_args()
    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    revalidator = UrlRevalidator(
        base_output_dir=output_dir,
        timeout=args.timeout,
        rate_limit_override=args.rate_limit,
    )

    t0 = time.time()
    all_summaries: Dict[str, Dict[str, int]] = {}

    for src in sources:
        def on_progress(current, total, res: UrlRevalidationResult):
            if current % 50 == 0 or current == total:
                sys.stdout.write(f"\r[{src.upper()}] Revalidando URL {current}/{total} ({res.status})...")
                sys.stdout.flush()

        out_path, summary = revalidator.revalidate_source(
            source=src,
            progress_callback=on_progress,
            force=args.force,
        )
        sys.stdout.write("\n")
        all_summaries[src] = summary

    elapsed = time.time() - t0

    # Guardar resumen global
    resumen_global = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed,
        "total_revalidated": sum(s.get("total_urls", 0) for s in all_summaries.values()),
        "summaries": all_summaries,
    }
    resumen_file = output_dir / "revalidacion_resumen.json"
    resumen_file.write_text(json.dumps(resumen_global, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.format in ("resumen", "tabla"):
        print_resumen_table(all_summaries, elapsed)
    else:
        print(json.dumps(resumen_global, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
