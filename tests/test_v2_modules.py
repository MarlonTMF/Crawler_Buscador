from pathlib import Path

from crawler.core.alert_notifier import AlertNotifier
from crawler.core.control_db import ControlDatabase, ResourceStatus
from crawler.core.drift_monitor import DriftMonitor
from crawler.core.form_automator import FormAutomator
from crawler.core.search_dorker import SearchDorker
from crawler.sources.generic_adapter import GenericSourceAdapter


def test_search_dorker_builds_document_queries():
    queries = SearchDorker.build_queries("example.org", ["pdf", "xlsx"])
    assert "site:example.org filetype:pdf" in queries[0]
    assert "filetype:xlsx" in queries[1]


def test_form_automator_generates_get_combinations():
    html = """
    <form action="/reportes">
      <select name="year"><option value="2025">2025</option><option value="2026">2026</option></select>
      <select name="month"><option value="01">Enero</option></select>
    </form>
    """
    urls = FormAutomator().generate_get_urls("https://example.org/base", html)
    assert "https://example.org/reportes?year=2025&month=01" in urls
    assert "https://example.org/reportes?year=2026&month=01" in urls


def test_drift_monitor_detects_structural_change():
    monitor = DriftMonitor(threshold=0.10)
    previous = "<html><body><nav><a href='/a'>A</a></nav></body></html>"
    current = "<html><body><main><section><table><tr><td>X</td></tr></table></section></main></body></html>"
    result = monitor.compare(previous, current)
    assert result.drift_detected is True
    assert len(result.fingerprint) == 64


def test_control_db_audits_resource(tmp_path: Path):
    db = ControlDatabase(tmp_path / "inventory.db")
    db.upsert_source("src", "Source", "https://example.org", "source.yaml")
    resource_id = db.upsert_resource(
        source_id="src",
        dataset_id="dataset",
        canonical_url="https://example.org/report.pdf",
        download_url="https://example.org/report.pdf",
        status=ResourceStatus.PROCESSED,
        content_sha256="a" * 64,
        file_size_bytes=10,
    )
    row = db.conn.execute("SELECT status FROM resource_audit_log WHERE resource_id = ?", (resource_id,)).fetchone()
    assert row["status"] == ResourceStatus.PROCESSED
    db.close()


def test_alert_notifier_writes_json_and_markdown(tmp_path: Path):
    path = AlertNotifier(tmp_path).notify("src", "drift", {"similarity": 0.5})
    assert path.exists()
    assert path.with_suffix(".md").exists()


def test_generic_adapter_classifies_from_yaml(tmp_path: Path):
    config_path = tmp_path / "source_generic.yaml"
    config_path.write_text(
        """
source:
  id: generic
  name: Generic
  base_url: https://example.org
  allowed_domains: [example.org]
crawl:
  seeds: [https://example.org]
classification:
  dataset_rules:
    - id: memorias
      url_patterns: ["/memorias/"]
      title_keywords: ["memoria"]
  excluded_path_keywords: ["/contacto"]
""",
        encoding="utf-8",
    )
    adapter = GenericSourceAdapter(config_path)
    assert adapter.is_url_excluded("https://example.org/contacto") is True
    assert adapter.classify_dataset("https://example.org/memorias/2025.pdf") == "memorias"
