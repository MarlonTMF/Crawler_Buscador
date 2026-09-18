import pytest
import requests

from crawler.core.discovery import DiscoveryEngine
from crawler.core.fetcher import HttpFetcher
from crawler.core.headless_fetcher import HeadlessFetchResult
from crawler.core.document_extractor import DocumentExtractor
from crawler.core.validation_engine import build_record_evidence, build_validation_summary


class DummyFetcher:
    def fetch_html(self, url):
        return True, 200, "<html><body></body></html>"

    def fetch_bytes(self, url):
        return True, 200, b""

    def fetch_head(self, url):
        return True, 200, {}


class DummyAdapter:
    def __init__(self):
        self.config = {
            "crawl": {
                "max_depth": 2,
                "max_pages": 20,
                "strategy": "bfs",
                "allowed_extensions": ["pdf", "xlsx", "xls", "csv", "zip"],
            },
            "classification": {"dataset_rules": [{"id": "reporte_financiero_mensual", "title_keywords": ["reporte financiero"]}]},
        }
        self.allowed_domains = ["www.finrural.org.bo"]
        self.allowed_extensions = ["pdf", "xlsx", "xls", "csv", "zip"]
        self.base_url = "https://www.finrural.org.bo"
        self.seeds = ["https://www.finrural.org.bo/archivos/"]

    def is_url_excluded(self, url):
        return False

    def classify_dataset(self, url, anchor_text=""):
        return "reporte_financiero_mensual"


def test_discovery_gives_real_document_links_a_high_organic_score():
    engine = DiscoveryEngine(DummyFetcher(), DummyAdapter())
    score = engine._score_link(
        "https://www.finrural.org.bo/documentos/reporte-financiero-mensual-2024.pdf",
        "Reporte financiero mensual 2024",
        "Descargar reporte financiero institucional",
        1,
    )
    is_download, ext = engine._is_download_link(
        "/documentos/reporte-financiero-mensual-2024.pdf",
        "Descargar reporte financiero mensual 2024",
    )

    assert is_download is True
    assert ext in {"pdf", "document"}
    assert score >= 6.0


def test_build_record_evidence_provides_url_signals():
    record = {
        "Fuente": "FINRURAL",
        "Url_Original": "https://example.com/reporte.pdf",
        "Final_Url": "https://example.com/reporte.pdf",
        "Score_Excel": 3.0,
        "Diagnosticos_Excel": ["documento encontrado", "fecha extraida"],
        "Robots_Allowed": True,
        "HTTP_Status": 200,
        "Doc_Links_Found_In_Seed": 4,
        "Subpage_Keywords_Found": 2,
    }

    evidence = build_record_evidence(record)

    assert evidence["score"] == 3.0
    assert any("documento encontrado" in signal.lower() for signal in evidence["signals"])
    assert any("4 enlaces" in signal for signal in evidence["signals"])
    assert any("HTTP status observado: 200" in signal for signal in evidence["signals"])


@pytest.fixture
def sample_records():
    return [
        {"Score_Excel": 0.0, "Diagnosticos_Excel": ["sin enlace directo", "bloqueo por robot.txt"]},
        {"Score_Excel": 1.0, "Diagnosticos_Excel": ["bloqueo por robot.txt"]},
        {"Score_Excel": 2.0, "Diagnosticos_Excel": ["documento encontrado"]},
        {"Score_Excel": 3.0, "Diagnosticos_Excel": ["documento encontrado", "fecha extraida"]},
        {"Score_Excel": 4.0, "Diagnosticos_Excel": ["documento encontrado", "fecha extraida", "url validada"]},
    ]


def test_build_validation_summary_counts_and_weaknesses(sample_records):
    summary = build_validation_summary(sample_records, baseline_rows=10)

    assert summary["total_records"] == 5
    assert summary["positive_cases"] == 4
    assert summary["success_rate"] == 0.8
    assert summary["score_distribution"]["0.0"] == 1
    assert summary["score_distribution"]["1.0"] == 1
    assert summary["score_distribution"]["2.0"] == 1
    assert summary["score_distribution"]["3.0"] == 1
    assert summary["score_distribution"]["4.0"] == 1
    assert "bloqueo por robot.txt" in summary["weaknesses"]
    assert summary["status"] in {"good", "needs_attention", "critical"}


def test_connection_failures_are_capped_below_valid_document_scores():
    record = {
        "Fuente": "FINRURAL",
        "Url_Original": "https://example.com/down",
        "Score_Excel": 4.0,
        "HTTP_Status": "CONN_ERROR",
        "Diagnosticos_Excel": ["sin enlace directo", "error de DNS"],
        "Robots_Allowed": False,
    }

    summary = build_validation_summary([record])
    effective = summary["record_evidence"][0]["score"]

    assert effective <= 2.0
    assert effective < 4.0
    assert "CONN_ERROR" in " ".join(summary["record_evidence"][0]["signals"]).upper()


@pytest.mark.live
def test_http_fetcher_validate_url_access_caps_connection_error(monkeypatch):
    fetcher = HttpFetcher()
    monkeypatch.setattr(fetcher, "is_url_allowed_by_robots", lambda url: True)

    def fake_head(url, timeout=None, allow_redirects=True):
        raise requests.exceptions.ConnectionError("simulated connection failure")

    class FakeResponse:
        status_code = 200
        text = "<html><body>ok</body></html>"
        headers = {}
        url = "https://example.com/page"
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        content = b"<html><body>ok</body></html>"

    def fake_get(url, timeout=None):
        raise requests.exceptions.ConnectionError("simulated connection failure")

    monkeypatch.setattr(fetcher.session, "head", fake_head)
    monkeypatch.setattr(fetcher.session, "get", fake_get)

    result = fetcher.validate_url_access("https://example.com/down")

    assert result["error_type"] in {"CONN_ERROR", "DNS_ERROR", "TIMEOUT"}
    assert result["effective_score"] <= 2.0
    assert result["reachable_http"] is False


def test_http_fetcher_exposes_real_document_counts(monkeypatch):
    fetcher = HttpFetcher()
    monkeypatch.setattr(fetcher, "is_url_allowed_by_robots", lambda url: True)

    class FakeResponse:
        status_code = 200
        text = (
            "<html><body><a href='/docs/reporte-financiero.pdf'>reporte</a>"
            "<a href='/docs/informe-anual.xlsx'>informe</a>"
            "<h1>Reporte financiero mensual</h1>"
            "<p>estadisticas activas del desarrollo</p></body></html>"
        )
        headers = {}
        url = "https://example.com/page"
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        content = text.encode("utf-8")

    def fake_head(url, timeout=None, allow_redirects=True):
        raise requests.exceptions.ConnectionError("head failed")

    def fake_get(url, timeout=None):
        return FakeResponse()

    monkeypatch.setattr(fetcher.session, "head", fake_head)
    monkeypatch.setattr(fetcher.session, "get", fake_get)

    result = fetcher.validate_url_access("https://example.com/page")

    assert result["reachable_http"] is True
    assert result["document_links_found"] >= 2
    assert len(result["keyword_hits"]) >= 2
    assert result["has_document_signal"] is True


def test_http_fetcher_uses_get_fallback_when_head_fails(monkeypatch):
    fetcher = HttpFetcher()
    monkeypatch.setattr(fetcher, "is_url_allowed_by_robots", lambda url: True)

    class FakeResponse:
        status_code = 200
        text = "<html><body>fallback ok</body></html>"
        headers = {}
        url = "https://example.com/fallback"
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        content = b"<html><body>fallback ok</body></html>"

    def fake_head(url, timeout=None, allow_redirects=True):
        raise requests.exceptions.ConnectionError("head failed")

    def fake_get(url, timeout=None):
        return FakeResponse()

    monkeypatch.setattr(fetcher.session, "head", fake_head)
    monkeypatch.setattr(fetcher.session, "get", fake_get)

    ok, status, text = fetcher.fetch_html("https://example.com/fallback")

    assert ok is True
    assert status == 200
    assert "fallback ok" in text


@pytest.mark.live
def test_browser_fallback_distinguishes_document_from_landing_page(monkeypatch):
    fetcher = HttpFetcher()
    monkeypatch.setattr(fetcher, "is_url_allowed_by_robots", lambda url: True)

    def fake_head(url, timeout=None, allow_redirects=True):
        raise requests.exceptions.ConnectionError("simulated connection failure")

    def fake_get(url, timeout=None):
        raise requests.exceptions.ConnectionError("simulated connection failure")

    class FakeHeadless:
        def fetch(self, url):
            return True, 200, HeadlessFetchResult(
                html=(
                    "<html><body><h1>Reporte financiero mensual</h1>"
                    "<a href='/docs/reporte-financiero.pdf'>Descargar reporte</a>"
                    "</body></html>"
                ),
                network_urls=["https://example.com/docs/reporte-financiero.pdf"],
            )

    monkeypatch.setattr(fetcher.session, "head", fake_head)
    monkeypatch.setattr(fetcher.session, "get", fake_get)

    result = fetcher.validate_url_access("https://example.com/reportes", browser_fallback=True, headless_fetcher=FakeHeadless())

    assert result["reachable_http"] is True
    assert result["has_document_signal"] is True
    assert result["effective_score"] >= 3.0

    landing = fetcher.validate_url_access(
        "https://example.com/institucion",
        browser_fallback=True,
        headless_fetcher=FakeHeadless(),
        force_browser_html="<html><body><h1>Institución financiera</h1><p>Bienvenido</p></body></html>",
    )

    assert landing["has_document_signal"] in {False, None}
    assert landing["effective_score"] <= 2.0


def test_document_extractor_turns_bytes_into_evidence():
    payload = b"Reporte financiero mensual del 2024\nInstituciones financieras del desarrollo\nTotal activo: 1250\n"
    extractor = DocumentExtractor()
    result = extractor.extract_document_evidence(payload, "https://example.com/reporte-financiero-2024.pdf", "pdf")

    assert result["has_evidence"] is True
    assert "reporte financiero" in result["snippet_text"].lower()
    assert "reporte" in result["keyword_hits"]
    assert result["quality_score"] >= 2.0


def test_build_record_evidence_exposes_document_evidence_for_ui():
    record = {
        "Fuente": "FINRURAL",
        "Url_Original": "https://example.com/reporte-financiero-2024.pdf",
        "Final_Url": "https://example.com/reporte-financiero-2024.pdf",
        "Score_Excel": 4.0,
        "HTTP_Status": 200,
        "Robots_Allowed": True,
        "Disegno": "validado",
        "Document_Evidence": {
            "file_type": "pdf",
            "keyword_hits": ["reporte", "financiero", "activo"],
            "snippet_text": "Reporte financiero mensual 2024 con activo consolidado.",
            "quality_score": 4.0,
        },
    }

    evidence = build_record_evidence(record)

    assert evidence["document_evidence"]["keyword_hits"] == ["activo", "financiero", "reporte"]
    assert "Reporte financiero mensual 2024" in evidence["document_evidence"]["snippet_text"]
    assert any("palabras clave documentales" in signal.lower() for signal in evidence["signals"])
