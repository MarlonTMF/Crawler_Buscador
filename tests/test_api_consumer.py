import json
from unittest.mock import MagicMock, patch
import pytest

from crawler.core.api_consumer import ApiConsumer
from crawler.core.discovery import DiscoveryEngine, DiscoveredCandidate


def test_extract_candidates_from_json_payload():
    sample_payload = {
        "data": [
            {
                "id": 1,
                "attributes": {
                    "titulo": "Estudio Agropecuario 2025",
                    "portada": {
                        "data": {
                            "attributes": {
                                "url": "/uploads/portada_thumb.png"
                            }
                        }
                    },
                    "documento": {
                        "data": {
                            "attributes": {
                                "url": "/uploads/estudio_agropecuario_2025.pdf"
                            }
                        }
                    },
                    "base_datos": {
                        "data": {
                            "attributes": {
                                "url": "https://ice.santacruz.gob.bo/uploads/precios_base.xlsx"
                            }
                        }
                    },
                    "sitio_externo": "https://otra-web.com/archivo.pdf"
                }
            }
        ],
        "meta": {
            "pagination": {
                "page": 1,
                "pageSize": 25,
                "pageCount": 1,
                "total": 1
            }
        }
    }

    consumer = ApiConsumer(
        base_url="https://ice.santacruz.gob.bo",
        allowed_domains=["ice.santacruz.gob.bo", "www.ice.santacruz.gob.bo"],
        allowed_extensions=["pdf", "xlsx", "xls", "csv", "zip"]
    )

    candidates = consumer.extract_candidates_from_payload(
        payload=sample_payload,
        endpoint_url="https://ice.santacruz.gob.bo/api/estudios?populate=*"
    )

    urls = [c.url for c in candidates]
    assert "https://ice.santacruz.gob.bo/uploads/estudio_agropecuario_2025.pdf" in urls
    assert "https://ice.santacruz.gob.bo/uploads/precios_base.xlsx" in urls
    # .png must be ignored (not in allowed_extensions)
    assert not any(u.endswith(".png") for u in urls)
    # external domain otra-web.com must be ignored
    assert "https://otra-web.com/archivo.pdf" not in urls
    # url_origin must be 'api'
    for c in candidates:
        assert c.url_origin == "api"


def test_no_regression_when_api_endpoints_missing():
    mock_adapter = MagicMock()
    mock_adapter.source_id = "test_source"
    mock_adapter.base_url = "https://test.gob.bo"
    mock_adapter.allowed_domains = ["test.gob.bo"]
    mock_adapter.allowed_extensions = ["pdf"]
    mock_adapter.seeds = ["https://test.gob.bo"]
    mock_adapter.api_endpoints = []  # No api endpoints configured
    mock_adapter.config = {
        "crawl": {
            "use_sitemaps": False,
            "use_wayback": False,
            "use_search_dorking": False,
            "api_endpoints": [],
        }
    }
    mock_adapter.classify_dataset.return_value = "default_dataset"
    mock_adapter.is_url_excluded.return_value = False

    mock_fetcher = MagicMock()
    mock_fetcher.fetch_html.return_value = (
        True,
        200,
        "<html><body><a href='https://test.gob.bo/doc.pdf'>Doc</a></body></html>",
    )

    discovery = DiscoveryEngine(fetcher=mock_fetcher, adapter=mock_adapter)

    with patch.object(ApiConsumer, "discover_from_endpoints") as mock_api_call:
        candidates = discovery.discover_from_seeds()
        mock_api_call.assert_not_called()
        assert len(candidates) >= 1


def test_strapi_pagination_respects_max_pages():
    consumer = ApiConsumer(
        base_url="https://ice.santacruz.gob.bo",
        allowed_domains=["ice.santacruz.gob.bo"],
        allowed_extensions=["pdf"],
        rate_limit_per_second=0,
    )

    page1_payload = {
        "data": [{"attributes": {"documento": {"data": {"attributes": {"url": "/uploads/doc1.pdf"}}}}}],
        "meta": {"pagination": {"page": 1, "pageSize": 1, "pageCount": 5, "total": 5}},
    }
    page2_payload = {
        "data": [{"attributes": {"documento": {"data": {"attributes": {"url": "/uploads/doc2.pdf"}}}}}],
        "meta": {"pagination": {"page": 2, "pageSize": 1, "pageCount": 5, "total": 5}},
    }

    mock_resp1 = MagicMock()
    mock_resp1.status_code = 200
    mock_resp1.json.return_value = page1_payload

    mock_resp2 = MagicMock()
    mock_resp2.status_code = 200
    mock_resp2.json.return_value = page2_payload

    with patch("requests.get", side_effect=[mock_resp1, mock_resp2]) as mock_get:
        with patch.object(consumer.robots_gate, "allowed", return_value=True):
            endpoints_cfg = [
                {
                    "url": "https://ice.santacruz.gob.bo/api/estudios?populate=*",
                    "pagination": "strapi_v4",
                    "max_pages": 2,
                }
            ]
            candidates = consumer.discover_from_endpoints(endpoints_cfg)
            assert len(candidates) == 2
            assert mock_get.call_count == 2
            urls = [c.url for c in candidates]
            assert "https://ice.santacruz.gob.bo/uploads/doc1.pdf" in urls
            assert "https://ice.santacruz.gob.bo/uploads/doc2.pdf" in urls

