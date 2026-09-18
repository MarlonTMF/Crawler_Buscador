"""Resuelve automáticamente dominios caídos del dataset maestro, con auditoría.

Para cada fuente indicada (o todas las que estén en CONN_ERROR si no se pasa
``--fuente``):

1. Le pregunta a Gemini qué pasó (¿se movió? ¿se disolvió? ¿quién asumió sus
   funciones?).
2. Si el candidato no responde tal cual, prueba variantes mecánicas (www,
   esquema, TLD) de ESE candidato — no solo del dominio original.
3. Verifica el contenido de cada candidato que sí responde contra palabras
   clave del nombre de la institución, para no aceptar un dominio que
   coincide de casualidad (caso real: "cadex.org" responde 200 pero es la
   Cámara de Exportadores de Santa Cruz, no la de Cochabamba).

Todo intento queda en ``output/url_resolution_log.json`` (historial completo,
con la respuesta cruda de la IA) sin importar el resultado. Solo los casos
con ``status: resolved`` (verificados por contenido) actualizan
automáticamente ``config/moved_urls.json`` y
``output/excel_urls_diagnostic.json``; los ``reachable_unverified`` se listan
para revisión humana pero NO se escriben como definitivos.

Uso:
    python resolve_dead_domains.py                       # todas las CONN_ERROR
    python resolve_dead_domains.py --fuente BOLCEREALES FAM CADEXCO
    python resolve_dead_domains.py --fuente IBCH --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from crawler.core.fetcher import HttpFetcher  # noqa: E402
from crawler.core.url_resolver import resolve_dead_domain  # noqa: E402

ROOT = Path(__file__).resolve().parent
DIAGNOSTIC_PATH = ROOT / "output" / "excel_urls_diagnostic.json"
MOVED_URLS_PATH = ROOT / "config" / "moved_urls.json"
LOG_PATH = ROOT / "output" / "url_resolution_log.json"


def load_records() -> list[dict]:
    return json.loads(DIAGNOSTIC_PATH.read_text(encoding="utf-8"))


def load_moved_urls() -> list[dict]:
    if MOVED_URLS_PATH.exists():
        return json.loads(MOVED_URLS_PATH.read_text(encoding="utf-8"))
    return []


def load_log() -> list[dict]:
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    return []


def pick_targets(records: list[dict], fuentes: list[str] | None) -> list[dict]:
    if fuentes:
        wanted = set(fuentes)
        return [r for r in records if r.get("Fuente") in wanted]
    return [r for r in records if str(r.get("HTTP_Status")) == "CONN_ERROR"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fuente", nargs="+", default=None, help="Nombre(s) de Fuente a resolver (default: todas en CONN_ERROR)")
    parser.add_argument("--dry-run", action="store_true", help="No escribe en moved_urls.json ni en el dataset maestro; solo loguea")
    parser.add_argument("--rate-limit", type=float, default=6.0, help="Segundos de espera entre consultas a Gemini (default 6s, por cuota)")
    args = parser.parse_args()

    records = load_records()
    targets = pick_targets(records, args.fuente)
    if not targets:
        print("No hay fuentes que resolver (¿ya están todas resueltas, o el --fuente no coincide con ningún registro?).")
        return

    fetcher = HttpFetcher(timeout=8, max_retries=1)
    if not fetcher.gemini_api_key:
        print("GEMINI_API_KEY no configurada en .env; no se puede continuar.")
        sys.exit(1)

    headless_fetcher = None
    try:
        from crawler.core.headless_fetcher import HeadlessFetcher
        headless_fetcher = HeadlessFetcher(timeout_ms=15000, scroll_steps=0)
    except Exception:
        pass  # Playwright no instalado: la verificación de sitios tipo SPA se degradará sin romper el flujo.

    log = load_log()
    moved_urls = load_moved_urls()
    records_by_fuente = {r.get("Fuente"): r for r in records}

    print(f"Resolviendo {len(targets)} fuente(s): {[t.get('Fuente') for t in targets]}\n")

    for i, rec in enumerate(targets):
        fuente = rec.get("Fuente")
        institucion = rec.get("Institucion") or ""
        original_url = rec.get("Url_Original") or rec.get("Final_Url")
        print(f"[{i + 1}/{len(targets)}] {fuente} ({institucion}) — {original_url}")

        result = resolve_dead_domain(fetcher, fuente, institucion, original_url, headless_fetcher=headless_fetcher)
        log.append(result)

        status = result["resolution"]["status"]
        resolved_url = result["resolution"]["resolved_url"]
        print(f"  -> {status}" + (f" : {resolved_url}" if resolved_url else ""))
        for q in result["ai_queries"]:
            reason = (q["response"].get("reason") or "")[:160]
            print(f"     IA ({q['kind']}): {reason}")

        if not args.dry_run and status == "resolved":
            moved_urls = [m for m in moved_urls if m.get("original") != original_url]
            moved_urls.append({
                "original": original_url,
                "resolved": resolved_url,
                "confidence": result["resolution"]["confidence"],
                "reason": next((q["response"].get("reason") for q in result["ai_queries"]), ""),
                "matched_keywords": next(
                    (c["matched_keywords"] for c in result["candidates"] if c["url"] == resolved_url), []
                ),
                "source": "resolve_dead_domains.py (gemini_verdict+variant_exchange+content_check)",
                "timestamp": result["timestamp"],
            })

            if fuente in records_by_fuente:
                target_rec = records_by_fuente[fuente]
                target_rec.update({
                    "Final_Url": resolved_url,
                    "HTTP_Status": 200,
                    "Diagnosticos_Excel": ["alternativa seleccionada", "acceso validado", "verificado por contenido"],
                    "mapped_from": original_url,
                    "mapping_resolved": resolved_url,
                    "mapping_source": result["resolution"]["method"],
                    "mapping_confidence": result["resolution"]["confidence"],
                    "mapping_timestamp": result["timestamp"],
                })
        elif not args.dry_run and status == "dissolved_no_successor":
            if fuente in records_by_fuente:
                # Preferir el motivo de la consulta de sucesor (más específico) sobre el
                # del veredicto inicial, que a veces es solo un mensaje de error de cuota.
                note = next(
                    (q["response"].get("reason") for q in result["ai_queries"] if q["kind"] == "successor_query"),
                    None,
                ) or next((q["response"].get("reason") for q in result["ai_queries"]), "")
                records_by_fuente[fuente].update({
                    "HTTP_Status": "DISUELTA",
                    "Diagnosticos_Excel": ["institucion disuelta", "sin sucesor unico confirmado"],
                    "mapping_note": note,
                    "mapping_timestamp": result["timestamp"],
                })

        if status == "reachable_unverified":
            print(f"     ATENCIÓN: {resolved_url} responde pero no se pudo confirmar que sea '{institucion}' por contenido. Revisar a mano antes de aceptarlo.")

        print()
        if i < len(targets) - 1:
            time.sleep(args.rate_limit)

    LOG_PATH.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Registro de auditoría actualizado: {LOG_PATH}")

    if not args.dry_run:
        MOVED_URLS_PATH.write_text(json.dumps(moved_urls, ensure_ascii=False, indent=2), encoding="utf-8")
        DIAGNOSTIC_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Actualizado: {MOVED_URLS_PATH}")
        print(f"Actualizado: {DIAGNOSTIC_PATH}")
    else:
        print("(--dry-run: no se escribió moved_urls.json ni el dataset maestro)")


if __name__ == "__main__":
    main()
