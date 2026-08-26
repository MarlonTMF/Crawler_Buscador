from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from crawler.core.validation_engine import build_record_evidence, build_validation_summary, load_json_records

ROOT = Path(__file__).resolve().parent
DASHBOARD_DIR = ROOT / "dashboard"
JSON_PATH = ROOT / "output" / "excel_urls_diagnostic.json"
BASELINE_PATH = ROOT / "resultadosPrimerCrawleoUnido.xlsx"


def _read_records_for_summary() -> dict:
    records = load_json_records(JSON_PATH)
    baseline_rows = 0
    if BASELINE_PATH.exists():
        try:
            from openpyxl import load_workbook

            wb = load_workbook(BASELINE_PATH, read_only=True, data_only=True)
            ws = wb.active
            baseline_rows = sum(
                1
                for row in ws.iter_rows(min_row=2, values_only=True)
                if any(value is not None for value in row)
            )
        except Exception:
            baseline_rows = 0

    summary = build_validation_summary(records, baseline_rows=baseline_rows)
    summary["records"] = [{**record, "evidence": build_record_evidence(record)} for record in records]
    return summary


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/summary":
            payload = json.dumps(_read_records_for_summary()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if parsed.path in {"/", "/index.html"}:
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, format, *args):
        # avoid noisy logs in terminal
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), DashboardHandler)
    print("Dashboard activo en http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Apagando dashboard...")
    finally:
        server.server_close()
