"""Genera un reporte de APIs detectadas (y su documentación) por institución.

Recorre la lista maestra de fuentes (por defecto ``output/excel_urls_diagnostic.json``,
la misma que usa el dashboard) y para cada dominio único:

1. Sondea rutas conocidas de API (``/api``, ``/wp-json``, ``/graphql``, ...) y de
   documentación (``/swagger.json``, ``/api-docs``, ``/redoc``, ...).
2. Revisa los enlaces del HTML de la portada en busca de menciones a API/documentación.
3. Opcionalmente (``--with-network-capture``), renderiza la portada con Playwright y
   observa las llamadas AJAX/fetch reales que dispara la página (requiere
   ``playwright install chromium`` una vez).

Escribe:
  - ``output/api_report.json``: datos crudos por institución.
  - ``output/api_report.md``: reporte legible para compartir con el cliente.
  - ``output/api_report.pdf`` (si se pasa ``--pdf``): versión PDF con tabla real,
    maquetada por scripts/render_api_report_pdf.py (no es una conversión de Markdown).

Uso:
    python generate_api_report.py
    python generate_api_report.py --limit 5 --with-network-capture --pdf
    python generate_api_report.py --input output/excel_urls_diagnostic.json
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from crawler.core.api_detector import (  # noqa: E402
    RobotsGate,
    merge_reports,
    probe_domain_for_apis,
    scan_html_for_api_links,
    scan_js_bundles_for_api_calls,
    scan_network_traffic_for_apis,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "output" / "excel_urls_diagnostic.json"
DEFAULT_OUTPUT_DIR = ROOT / "output"


def load_sources(input_path: Path) -> list[dict]:
    records = json.loads(input_path.read_text(encoding="utf-8"))
    seen_domains = set()
    sources = []
    for r in records:
        url = r.get("Final_Url") or r.get("Url_Original") or r.get("url")
        if not url or not str(url).startswith("http"):
            continue
        domain = urlparse(url).netloc
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        sources.append({
            "fuente": r.get("Fuente") or r.get("fuente") or domain,
            "institucion": r.get("Institucion") or "",
            "url": url,
        })
    return sources


def fetch_homepage_html(url: str, timeout: int = 10) -> str | None:
    try:
        resp = requests.get(url, timeout=(min(5, timeout), timeout), headers={"User-Agent": "DataxProspectorBot/1.0 (+api-report)"})
        if resp.status_code < 400:
            return resp.text
    except Exception:
        return None
    return None


def analyze_source(source: dict, robots_gate: RobotsGate, timeout: int, rate_limit: float,
                    with_network_capture: bool) -> dict:
    url = source["url"]
    report = probe_domain_for_apis(url, timeout=timeout, rate_limit_seconds=rate_limit, robots_gate=robots_gate)

    html = fetch_homepage_html(url, timeout=timeout)
    link_findings = scan_html_for_api_links(html, url)
    js_findings = scan_js_bundles_for_api_calls(html, url, timeout=timeout)
    merge_reports(report, link_findings, js_findings)

    if with_network_capture:
        report.network_capture_attempted = True
        try:
            from crawler.core.headless_fetcher import HeadlessFetcher
            ok, _status, result = HeadlessFetcher(timeout_ms=20000, scroll_steps=1).fetch(url)
            if ok and result is not None:
                network_findings = scan_network_traffic_for_apis(result.network_responses or [
                    {"url": u} for u in result.network_urls
                ], base_url=url)
                merge_reports(report, network_findings)
                report.network_capture_ok = True
        except Exception as exc:
            report.errors.append(f"network-capture: {exc}")

    data = report.to_dict()
    data["fuente"] = source["fuente"]
    data["institucion"] = source["institucion"]
    return data


def render_markdown(results: list[dict], generated_at: str) -> str:
    total = len(results)
    with_api = [r for r in results if r["has_api"]]
    with_docs = [r for r in results if r["has_documentation"]]

    lines = []
    lines.append("# Reporte de APIs detectadas")
    lines.append("")
    lines.append(f"Generado: {generated_at}")
    lines.append("")
    lines.append("## Resumen")
    lines.append("")
    lines.append(f"- Instituciones analizadas: {total}")
    lines.append(f"- Con API detectada: {len(with_api)}")
    lines.append(f"- Con documentación de API detectada: {len(with_docs)}")
    lines.append("")
    lines.append("| Fuente | Institución | API detectada | Endpoints | Documentación |")
    lines.append("|---|---|---|---|---|")
    for r in results:
        api_flag = "Sí" if r["has_api"] else "No"
        doc_flag = "Sí" if r["has_documentation"] else "No"
        lines.append(f"| {r['fuente']} | {r['institucion']} | {api_flag} | {len(r['endpoints'])} | {doc_flag} |")
    lines.append("")
    lines.append("## Detalle por institución")
    lines.append("")

    for r in results:
        lines.append(f"### {r['fuente']} — {r['institucion'] or r['base_url']}")
        lines.append("")
        lines.append(f"Sitio: {r['base_url']}")
        lines.append("")
        if r["has_api"]:
            lines.append("**APIs / endpoints detectados:**")
            lines.append("")
            for e in r["endpoints"]:
                extra = f" — {e['note']}" if e.get("note") else ""
                ct = f" ({e['content_type']})" if e.get("content_type") else ""
                lines.append(f"- `{e['url']}`{ct} · fuente: {e['source']}{extra}")
            lines.append("")
        else:
            lines.append("No se detectó ninguna API en este sitio con los métodos usados.")
            lines.append("")

        if r["has_documentation"]:
            lines.append("**Documentación de API encontrada:**")
            lines.append("")
            for d in r["documentation"]:
                title = f" — {d['title']}" if d.get("title") else ""
                lines.append(f"- `{d['url']}`{title} · fuente: {d['source']}")
            lines.append("")
        else:
            lines.append("No se encontró documentación de API (Swagger/OpenAPI/Redoc, etc.).")
            lines.append("")

        if r.get("robots_blocked_paths"):
            lines.append(f"_Rutas no sondeadas por robots.txt: {len(r['robots_blocked_paths'])}_")
            lines.append("")
        if r.get("errors"):
            lines.append(f"_Errores durante el sondeo: {len(r['errors'])}_")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Genera un reporte de APIs y documentación detectadas por institución.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="JSON maestro de fuentes (default: output/excel_urls_diagnostic.json)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directorio de salida (default: output/)")
    parser.add_argument("--limit", type=int, default=None, help="Analizar solo las primeras N fuentes (para pruebas)")
    parser.add_argument("--timeout", type=int, default=10, help="Timeout por request en segundos")
    parser.add_argument("--rate-limit", type=float, default=0.4, help="Segundos de espera entre requests al mismo dominio")
    parser.add_argument("--with-network-capture", action="store_true", help="Además, capturar tráfico de red real con Playwright (requiere navegador instalado)")
    parser.add_argument("--workers", type=int, default=6, help="Instituciones analizadas en paralelo (default: 6). Usar 1 para desactivar concurrencia.")
    parser.add_argument("--pdf", action="store_true", help="También generar output/api_report.pdf")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"No se encontró el archivo de entrada: {args.input}")
        sys.exit(1)

    sources = load_sources(args.input)
    if args.limit:
        sources = sources[: args.limit]

    # La captura de red con Playwright lanza un navegador por sitio: en paralelo alto
    # consume mucha RAM/CPU, así que la limitamos a un puñado de workers concurrentes.
    workers = min(args.workers, 3) if args.with_network_capture else args.workers
    print(f"Analizando {len(sources)} dominios únicos con {workers} worker(s) en paralelo...")
    robots_gate = RobotsGate()
    results_by_index: dict[int, dict] = {}

    def _run(i: int, source: dict) -> tuple[int, dict]:
        try:
            data = analyze_source(source, robots_gate, args.timeout, args.rate_limit, args.with_network_capture)
        except Exception as exc:
            data = {
                "base_url": source["url"], "has_api": False, "has_documentation": False,
                "endpoints": [], "documentation": [], "robots_blocked_paths": [],
                "errors": [str(exc)], "network_capture_attempted": args.with_network_capture,
                "network_capture_ok": False, "fuente": source["fuente"], "institucion": source["institucion"],
            }
        return i, data

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_run, i, source) for i, source in enumerate(sources)]
        done = 0
        for future in as_completed(futures):
            i, data = future.result()
            results_by_index[i] = data
            done += 1
            api_flag = "API detectada" if data["has_api"] else "sin API"
            doc_flag = "con docs" if data["has_documentation"] else "sin docs"
            print(f"[{done}/{len(sources)}] {data['fuente']} -> {api_flag}, {doc_flag}")

    results = [results_by_index[i] for i in range(len(sources))]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "api_report.json"
    md_path = args.output_dir / "api_report.md"

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    json_path.write_text(json.dumps({"generated_at": generated_at, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(results, generated_at), encoding="utf-8")
    print(f"\nEscrito: {json_path}")
    print(f"Escrito: {md_path}")

    if args.pdf:
        sys.path.insert(0, str(ROOT / "scripts"))
        from render_api_report_pdf import render_api_report_pdf  # noqa: E402
        pdf_path = args.output_dir / "api_report.pdf"
        render_api_report_pdf(results, generated_at, str(pdf_path))
        print(f"Escrito: {pdf_path}")

    total = len(results)
    with_api = sum(1 for r in results if r["has_api"])
    with_docs = sum(1 for r in results if r["has_documentation"])
    print(f"\nResumen: {with_api}/{total} sitios con API detectada, {with_docs}/{total} con documentación de API.")


if __name__ == "__main__":
    main()
