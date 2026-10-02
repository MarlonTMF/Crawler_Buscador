#!/usr/bin/env python3
"""
scripts/vigencia_spim.py

Vigencia de las series de producción de DATAX según el catálogo de SPIM.

Responde a la pregunta de la reunión del 2026-09-23 —«las DB de DATAX deben
estar al día»— sobre el catálogo oficial, no sobre uno inferido: para cada
serie de SPIM toma su periodicidad y la fecha hasta la que está actualizada, y
la compara con la fecha de la foto del respaldo.

La referencia por defecto es la fecha de la foto (la última modificación
registrada en SPIM), no la fecha de hoy: ``updated_to`` describe el estado de
SPIM en el momento del respaldo.

Uso:
    python scripts/vigencia_spim.py
    python scripts/vigencia_spim.py --institutions bcb,ine,asfi --format json --output output/vigencia_spim.json
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler.core.spim_catalog import (  # noqa: E402
    TOLERANCIA_MESES,
    evaluate_currency,
    load_spim_series,
    snapshot_date,
)

ESTADOS = ("AL_DIA", "ATRASADA", "FECHA_FUTURA", "SIN_FECHA", "SIN_PERIODICIDAD")


def main() -> int:
    ap = argparse.ArgumentParser(description="Vigencia de las series de SPIM por institución")
    ap.add_argument("--backup", type=Path, default=ROOT / "backup_10.0.0.12")
    ap.add_argument("--institutions", default="bcb,ine,asfi")
    ap.add_argument("--ref-date", help="Fecha de referencia AAAA-MM-DD (por defecto, la foto del respaldo)")
    ap.add_argument("--format", choices=("table", "json"), default="table")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    if not args.backup.exists():
        print(f"No se encuentra el respaldo de SPIM en {args.backup}", file=sys.stderr)
        return 2

    series = load_spim_series(args.backup)
    foto = snapshot_date(series)
    ref = date.fromisoformat(args.ref_date) if args.ref_date else foto
    wanted = [i.strip().lower() for i in args.institutions.split(",") if i.strip()]

    evals = [evaluate_currency(s, ref) for s in series if s.institution in wanted]
    resumen = {inst: collections.Counter() for inst in wanted}
    for e in evals:
        resumen[e.series.institution][e.status] += 1

    payload = {
        "fecha_foto_respaldo": foto.isoformat() if foto else None,
        "fecha_referencia": ref.isoformat() if ref else None,
        "tolerancia_meses": TOLERANCIA_MESES,
        "series_totales_spim": len(series),
        "series_sin_institucion_reconocida": sum(1 for s in series if s.institution is None),
        "resumen": {k: {est: v.get(est, 0) for est in ESTADOS} | {"total": sum(v.values())}
                    for k, v in resumen.items()},
        "series": [
            {
                "institucion": e.series.institution,
                "codigo": e.series.code,
                "nombre": e.series.name,
                "periodicidad": e.series.periodicity,
                "actualizada_hasta": e.series.updated_to.isoformat() if e.series.updated_to else None,
                "meses_desde_actualizacion": e.months_behind,
                "tolerancia_meses": e.tolerance_months,
                "estado": e.status,
                "estado_declarado_en_spim": e.series.state,
                "url": e.series.url,
                "ultima_url_descargada": e.series.last_file_url,
            }
            for e in sorted(evals, key=lambda x: (x.series.institution, x.status, -(x.months_behind or 0)))
        ],
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"Foto del respaldo: {payload['fecha_foto_respaldo']} · referencia: {payload['fecha_referencia']}")
    print(f"Series en SPIM: {len(series)} · sin institución reconocida por dominio: "
          f"{payload['series_sin_institucion_reconocida']}\n")
    print(f"{'Institución':12}" + "".join(f"{e:>18}" for e in ESTADOS) + f"{'Total':>8}")
    for inst, r in payload["resumen"].items():
        print(f"{inst.upper():12}" + "".join(f"{r[e]:>18}" for e in ESTADOS) + f"{r['total']:>8}")
    atrasadas = [s for s in payload["series"] if s["estado"] == "ATRASADA"]
    if atrasadas:
        print(f"\nSeries atrasadas ({len(atrasadas)}), de mayor a menor atraso:")
        for s in sorted(atrasadas, key=lambda x: -x["meses_desde_actualizacion"]):
            print(f"  {s['institucion']:5} {s['periodicidad']:10} hasta {s['actualizada_hasta']}  "
                  f"{s['meses_desde_actualizacion']:>6} meses  {s['nombre'][:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
