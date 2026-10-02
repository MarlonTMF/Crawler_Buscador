#!/usr/bin/env python3
"""
scripts/construir_vigilancia.py

Arma los datos de la interfaz de vigilancia (dashboard/vigilancia/) a partir de
las mediciones reales del proyecto. No inventa ni completa nada: si un dato no
existe en las fuentes, la interfaz lo muestra como ausente.

Fuentes:
  - output/revalidacion_{bcb,ine,asfi}.json   estado de las URLs catalogadas
  - output/vigencia_spim.json                 vigencia de las series de SPIM
  - scripts/detectar_huecos.py (en vivo)      períodos faltantes por serie
  - output/recup_b65.json                     última corrida completa de recuperación

Dos comprobaciones contra los servidores, guardadas en caché
(output/vigilancia_cache.json) y repetibles con --refrescar:
  - el nombre de archivo que el servidor declara para cada recuperación
    (Content-Disposition), que decide si la recuperación es válida;
  - si el último archivo descargado de cada serie atrasada sigue disponible.

Salida: dashboard/vigilancia/data.js (gitignorado: contiene datos del catálogo
de producción de SPIM y no debe publicarse).

Uso:
    python scripts/construir_vigilancia.py
    python scripts/construir_vigilancia.py --refrescar
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

import requests
import urllib3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler.core.gap_detector import GapDetector  # noqa: E402
from crawler.core.recovery_ladder import _served_filename  # noqa: E402

urllib3.disable_warnings()

PORTALES = ("bcb", "ine", "asfi")
NOMBRES = {
    "bcb": "Banco Central de Bolivia",
    "ine": "Instituto Nacional de Estadística",
    "asfi": "Autoridad de Supervisión del Sistema Financiero",
}
ESTRATEGIAS = {
    1: "Dirección conocida",
    2: "Plantilla de la serie",
    3: "Candidatos derivados de la serie",
    4: "Archivo histórico de la web",
    5: "Consulta a un modelo de lenguaje",
}
YEAR = re.compile(r"(?:^|[^\d])(19\d\d|20\d\d)(?:[^\d]|$)")
OUT = ROOT / "output"
CACHE = OUT / "vigilancia_cache.json"
DESTINO = ROOT / "dashboard" / "vigilancia" / "data.js"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _sesion():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (DATAX vigilancia)"
    return s


def _nombre_servido(url: str) -> dict:
    try:
        r = _sesion().get(url, stream=True, timeout=40, verify=False, allow_redirects=True)
        info = {"http": r.status_code, "servido": _served_filename(r), "url_final": r.url}
        r.close()
        return info
    except Exception as e:  # noqa: BLE001
        return {"http": None, "servido": None, "error": type(e).__name__}


def _estado_url(url: str) -> str:
    try:
        s = _sesion()
        r = s.head(url, timeout=25, allow_redirects=True, verify=False)
        if r.status_code in (403, 405):
            r = s.get(url, timeout=25, stream=True, verify=False)
            r.close()
        return "DISPONIBLE" if r.status_code == 200 else f"HTTP {r.status_code}"
    except Exception:  # noqa: BLE001
        return "SIN_RESPUESTA"


def _verificar(recup: dict, vigencia: dict, refrescar: bool) -> dict:
    cache = (_load(CACHE) or {}) if not refrescar else {}
    servidos = cache.get("servidos", {})
    enlaces = cache.get("enlaces", {})

    pend = [r["url"] for r in (recup or {}).get("recoveries", []) if r["url"] not in servidos]
    if pend:
        print(f"Comprobando el archivo servido de {len(pend)} recuperaciones…")
        with cf.ThreadPoolExecutor(6) as ex:
            for u, info in zip(pend, ex.map(_nombre_servido, pend)):
                servidos[u] = info

    urls = set()
    for s in (vigencia or {}).get("series", []):
        if s["estado"] == "ATRASADA":
            for u in (s.get("ultima_url_descargada") or s.get("url") or "").split(";"):
                if u.strip().startswith("http"):
                    urls.add(u.strip())
    pend = [u for u in urls if u not in enlaces]
    if pend:
        print(f"Comprobando {len(pend)} enlaces de series atrasadas…")
        with cf.ThreadPoolExecutor(8) as ex:
            for u, st in zip(pend, ex.map(_estado_url, pend)):
                enlaces[u] = st

    cache = {"actualizado": datetime.now(timezone.utc).isoformat(), "servidos": servidos, "enlaces": enlaces}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache


def _humano(dataset_id: str) -> str:
    t = dataset_id.replace("_", " ").strip()
    return t[:1].upper() + t[1:]


def _revalidacion() -> dict:
    res = {}
    for p in PORTALES:
        d = _load(OUT / f"revalidacion_{p}.json")
        if not d:
            res[p] = None
            continue
        items = d.get("results", [])
        res[p] = {
            "fecha": d.get("revalidated_at"),
            "resumen": d.get("summary", {}),
            "total": d.get("total_urls", len(items)),
            "detalle": [
                {k: it.get(k) for k in ("url", "status", "http_status", "final_url", "content_type",
                                        "error_message", "dataset_id")}
                for it in items if it.get("status") != "VIGENTE"
            ],
        }
    return res


def _faltantes() -> dict:
    import os
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "detectar_huecos.py"), "--format", "json"],
                          capture_output=True, cwd=ROOT, env=env)
    salida = proc.stdout.decode("utf-8", errors="replace")
    data = json.loads(salida[salida.index("{"):])
    series = []
    for portal, info in data["sources"].items():
        for ds in (info if isinstance(info, list) else info.get("datasets", [])):
            first, last, per = ds.get("first_observed_period"), ds.get("last_observed_period"), ds.get("periodicity")
            esperados = []
            if first and last and per not in (None, "eventual"):
                try:
                    esperados = GapDetector.generate_expected_periods(first, last, per)
                except Exception:  # noqa: BLE001
                    esperados = []
            recuperados = []
            db = OUT / portal / "inventory.db"
            if db.exists() and per not in (None, "eventual"):
                import sqlite3
                with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
                    for (ps,) in c.execute("SELECT period_start FROM resource_audit_log WHERE dataset_id = ? "
                                           "AND status = 'RECUPERADO_VIA_ESCALERA'", (ds["dataset_id"],)):
                        tok = GapDetector.date_to_period_token(ps, per) if ps else None
                        if tok:
                            recuperados.append(tok)
            series.append({
                "portal": portal,
                "dataset_id": ds["dataset_id"],
                "recuperados": sorted(set(recuperados)),
                "excluidos_del_calendario": ds.get("excluded_from_calendar", 0),
                "nombre": _humano(ds["dataset_id"]),
                "periodicidad": per,
                "tolerancia": ds.get("tolerance"),
                "primero": first,
                "ultimo": last,
                "esperados": esperados,
                "faltantes": ds.get("intermediate_gaps") or [],
                "atraso_periodos": ds.get("delay_periods"),
                "estado": ds.get("state"),
                "recursos": ds.get("total_resources"),
            })
    return {"fecha_referencia": data.get("reference_date"), "series": series}


def _recuperacion(recup: dict, cache: dict) -> dict:
    if not recup:
        return None
    verificadas, descartadas = [], []
    for r in recup.get("recoveries", []):
        chk = cache["servidos"].get(r["url"], {})
        servido = chk.get("servido")
        anios_srv = set(YEAR.findall(servido or ""))
        anios_per = set(YEAR.findall(str(r["period"])))
        fila = {
            "portal": r["portal"], "dataset_id": r["dataset_id"], "periodo": r["period"],
            "estrategia": r["recovery_rung"], "url": r["url"], "bytes": r.get("file_size_bytes"),
            "sha256": r.get("content_sha256"), "servido": servido, "http": chk.get("http"),
        }
        if anios_srv and anios_per and not (anios_srv & anios_per):
            fila["motivo"] = "El servidor entregó un documento de otro año"
            descartadas.append(fila)
        else:
            verificadas.append(fila)
    rechazos = [
        {"portal": x["portal"], "dataset_id": x["dataset_id"], "periodo": x["period"], "estrategia": x["source_rung"],
         "url": x["url"], "motivo": x["motivo"].split(":")[0], "detalle": x["motivo"]}
        for x in recup.get("rechazos_calidad", [])
    ]
    por_estrategia = []
    for n, nombre in ESTRATEGIAS.items():
        por_estrategia.append({
            "n": n, "nombre": nombre,
            "reportados": sum(1 for r in recup["recoveries"] if r["recovery_rung"] == n),
            "verificados": sum(1 for r in verificadas if r["estrategia"] == n),
            "descartados_servidor": sum(1 for r in descartadas if r["estrategia"] == n),
            "rechazados_compuertas": sum(1 for r in rechazos if r["estrategia"] == n),
        })
    return {
        "fecha_corrida": recup.get("timestamp"),
        "segundos": recup.get("elapsed_seconds"),
        "verificadas": verificadas,
        "descartadas": descartadas,
        "rechazos_compuertas": rechazos,
        "por_estrategia": por_estrategia,
        "agente": recup.get("agent_stats"),
        "agente_consultas": [
            {"portal": q["portal"], "dataset_id": q["dataset_id"], "periodo": q["period"],
             "propuestos": q.get("candidatos_propuestos"), "candidatos": q.get("candidatos", [])[:5],
             "pasaron_head": q.get("pasaron_head")}
            for q in recup.get("agent_query_log", [])
        ],
        "herencia_candidatos": recup.get("inheritance_candidates_count"),
    }


def _vigencia(vig: dict, cache: dict) -> dict:
    if not vig:
        return None
    series = []
    for s in vig["series"]:
        fila = dict(s)
        if s["estado"] == "ATRASADA":
            urls = [u.strip() for u in (s.get("ultima_url_descargada") or s.get("url") or "").split(";")
                    if u.strip().startswith("http")]
            ests = [cache["enlaces"].get(u) for u in urls]
            if not urls or any(e is None for e in ests):
                fila["ultimo_archivo"] = None
            elif all(e == "DISPONIBLE" for e in ests):
                fila["ultimo_archivo"] = "DISPONIBLE"
            else:
                fila["ultimo_archivo"] = "NO_DISPONIBLE"
            fila["enlaces"] = [{"url": u, "estado": cache["enlaces"].get(u)} for u in urls]
        series.append(fila)
    return {k: vig[k] for k in ("fecha_foto_respaldo", "fecha_referencia", "tolerancia_meses", "resumen")} | {"series": series}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--refrescar", action="store_true", help="Repite las comprobaciones contra los servidores")
    args = ap.parse_args()

    recup = _load(OUT / "recup_b65.json")
    vig = _load(OUT / "vigencia_spim.json")
    cache = _verificar(recup, vig, args.refrescar)

    datos = {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "verificado_en": cache["actualizado"],
        "portales": [{"id": p, "nombre": NOMBRES[p]} for p in PORTALES],
        "revalidacion": _revalidacion(),
        "vigencia": _vigencia(vig, cache),
        "faltantes": _faltantes(),
        "recuperacion": _recuperacion(recup, cache),
        "estrategias": ESTRATEGIAS,
    }
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text("window.VIGILANCIA = " + json.dumps(datos, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"Datos escritos en {DESTINO.relative_to(ROOT)}")
    rec = datos["recuperacion"] or {}
    print(f"  recuperaciones verificadas: {len(rec.get('verificadas', []))} · descartadas: {len(rec.get('descartadas', []))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
