#!/usr/bin/env python3
"""
scripts/incorporar_recuperaciones.py

Incorpora al inventario de cada portal las recuperaciones verificadas, para que
el detector de faltantes las cuente y el mapa exportado al interno las incluya.

Sin este paso, un período recuperado sigue apareciendo como faltante y, peor,
el calendario de la serie puede quedar mal anclado: si el único documento de la
serie que figura en el inventario es el más reciente, los huecos anteriores no
se ven.

Cada recuperación se vuelve a comprobar contra el servidor antes de escribir:
se admite solo si el nombre de archivo que el servidor declara
(Content-Disposition o URL final) no contradice el año del período. Es la misma
regla que la compuerta ano_servido_contradictorio de la escalera.

Las filas se insertan con estado RECUPERADO_VIA_ESCALERA. La operación es
idempotente: una URL ya presente en el inventario no se vuelve a insertar.

Uso:
    python scripts/incorporar_recuperaciones.py --input output/recup_b65.json
    python scripts/incorporar_recuperaciones.py --input output/recup_b65.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import urllib3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler.core.recovery_ladder import _served_filename  # noqa: E402

urllib3.disable_warnings()
YEAR = re.compile(r"(?:^|[^\d])(19\d\d|20\d\d)(?:[^\d]|$)")
ESTADO = "RECUPERADO_VIA_ESCALERA"


def limites_periodo(periodo: str) -> tuple[str, str]:
    """'2025-S2' -> ('2025-07-01','2025-12-31'); '2024-Q3', '2025-11', '2025' análogos."""
    p = str(periodo)
    y = int(p[:4])
    if "-S" in p:
        s = int(p.split("-S")[1])
        return (f"{y}-01-01", f"{y}-06-30") if s == 1 else (f"{y}-07-01", f"{y}-12-31")
    if "-Q" in p:
        q = int(p.split("-Q")[1])
        ini_m = 3 * (q - 1) + 1
        fin = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[q]
        return f"{y}-{ini_m:02d}-01", f"{y}-{fin}"
    if re.fullmatch(r"\d{4}-\d{2}", p):
        m = int(p[5:])
        import calendar
        return f"{y}-{m:02d}-01", f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
    return f"{y}-01-01", f"{y}-12-31"


def verificar(url: str, periodo: str) -> tuple[bool, str]:
    try:
        s = requests.Session()
        s.headers["User-Agent"] = "Mozilla/5.0 (DATAX)"
        r = s.get(url, stream=True, timeout=40, verify=False, allow_redirects=True)
        servido = _served_filename(r)
        ok_http = r.status_code in (200, 206)
        r.close()
    except Exception as e:  # noqa: BLE001
        return False, f"sin respuesta ({type(e).__name__})"
    if not ok_http:
        return False, f"HTTP {r.status_code}"
    a_srv, a_per = set(YEAR.findall(servido or "")), set(YEAR.findall(periodo))
    if a_srv and a_per and not (a_srv & a_per):
        return False, f"el servidor entrega '{servido}'"
    return True, servido


def main() -> int:
    ap = argparse.ArgumentParser(description="Incorpora recuperaciones verificadas al inventario")
    ap.add_argument("--input", type=Path, default=ROOT / "output" / "recup_b65.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    insertadas = rechazadas = existentes = 0
    for r in data.get("recoveries", []):
        db = ROOT / "output" / r["portal"] / "inventory.db"
        conn = sqlite3.connect(db)
        try:
            if conn.execute("SELECT 1 FROM resource_audit_log WHERE canonical_url = ?", (r["url"],)).fetchone():
                existentes += 1
                continue
            ok, detalle = verificar(r["url"], str(r["period"]))
            if not ok:
                rechazadas += 1
                print(f"  rechazada  {r['portal']}/{r['dataset_id']} {r['period']}: {detalle}")
                continue
            ini, fin = limites_periodo(r["period"])
            fila = (
                f"{r['portal']}:{r['dataset_id']}:{r['period']}:recuperado",
                r["portal"], r["dataset_id"], r["url"], r["url"], ESTADO,
                r.get("content_sha256"), r.get("file_size_bytes"), ini, fin, "high",
                None, None, datetime.now(timezone.utc).isoformat(),
            )
            print(f"  {'(simulacro) ' if args.dry_run else ''}incorporada {r['portal']}/{r['dataset_id']} {r['period']} <- {detalle}")
            if not args.dry_run:
                conn.execute(
                    "INSERT INTO resource_audit_log (resource_id, source_id, dataset_id, canonical_url, download_url, "
                    "status, content_sha256, file_size_bytes, period_start, period_end, date_confidence_score, "
                    "error_code, error_stackTrace, execution_timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", fila)
                conn.commit()
            insertadas += 1
        finally:
            conn.close()
    print(f"Incorporadas: {insertadas} · rechazadas: {rechazadas} · ya presentes: {existentes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
