"""
tests/test_headless_fetcher.py
==============================
Pruebas unitarias para la integración de renderizado headless (Playwright)
en el motor de extracción (Etapa C / B-13).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from crawler.core.headless_fetcher import HeadlessFetcher, HeadlessFetchResult
from crawler.core.fetcher import HttpFetcher
from crawler.sources.base_adapter import BaseSourceAdapter
from crawler.core.orchestrator import CrawlOrchestrator


class DummyAdapter(BaseSourceAdapter):
    def is_url_excluded(self, url: str) -> bool:
        return False

    def classify_dataset(self, url: str, anchor_text: str = ""):
        return "test_dataset"


def test_headless_fetcher_defaults():
    fetcher = HeadlessFetcher()
    assert fetcher.wait_until == "domcontentloaded", "D-03: wait_until debe ser 'domcontentloaded'"
    assert "Mozilla" in fetcher.user_agent, "Debe tener un User-Agent realista"
    assert fetcher.timeout_ms == 30000


def test_base_adapter_use_playwright_property(tmp_path: Path):
    cfg_file = tmp_path / "source_test.yaml"
    cfg_file.write_text(
        """
source:
  id: test_src
  name: "Test Source"
  base_url: "https://example.com"
crawl:
  seeds: ["https://example.com"]
  use_playwright: true
""",
        encoding="utf-8",
    )
    adapter = DummyAdapter(cfg_file)
    assert adapter.use_playwright is True

    cfg_file_no_pw = tmp_path / "source_no_pw.yaml"
    cfg_file_no_pw.write_text(
        """
source:
  id: test_src_no
  name: "Test Source No PW"
  base_url: "https://example.com"
crawl:
  seeds: ["https://example.com"]
  use_playwright: false
""",
        encoding="utf-8",
    )
    adapter_no_pw = DummyAdapter(cfg_file_no_pw)
    assert adapter_no_pw.use_playwright is False


def test_http_fetcher_delegates_to_headless_when_enabled():
    mock_headless = MagicMock(spec=HeadlessFetcher)
    mock_headless.fetch.return_value = (
        True,
        200,
        HeadlessFetchResult(html="<html><head><title>Headless OK</title></head><body>Content</body></html>"),
    )

    fetcher = HttpFetcher(
        use_playwright=True,
        headless_fetcher=mock_headless,
        honor_robots_txt=False,
    )

    ok, status, html = fetcher.fetch_html("https://example.com/portal")
    assert ok is True
    assert status == 200
    assert "Headless OK" in html
    mock_headless.fetch.assert_called_once_with("https://example.com/portal")


def test_orchestrator_initializes_fetcher_with_use_playwright(tmp_path: Path):
    cfg_file = tmp_path / "source_pw.yaml"
    cfg_file.write_text(
        """
source:
  id: pw_src
  name: "Playwright Source"
  base_url: "https://example.com"
crawl:
  seeds: ["https://example.com"]
  use_playwright: true
audit:
  enabled: false
""",
        encoding="utf-8",
    )
    adapter = DummyAdapter(cfg_file)
    orchestrator = CrawlOrchestrator(adapter=adapter, output_dir=tmp_path)

    assert hasattr(orchestrator.fetcher, "use_playwright")
    assert orchestrator.fetcher.use_playwright is True
