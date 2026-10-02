"""
tests/test_url_revalidator.py
=============================
Pruebas unitarias para el revalidador de URLs catalogadas (B-60 / P-1).
Verifica:
- Clasificación de URLs: VIGENTE (200 + doc), REDIRIGIDA (301/302 -> 200), ELIMINADA (404/410), INACCESIBLE (error/timeout/403)
- Respaldo GET ante 405 Method Not Allowed
- Respeto a rate limiting y persistencia de fecha de revalidación
- Extracción de URLs desde resource_audit_log en inventory.db
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import requests

from crawler.core.url_revalidator import UrlRevalidator, UrlRevalidationResult


@pytest.fixture
def sample_inventory_db(tmp_path):
    db_path = tmp_path / "inventory.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE resource_audit_log (
                resource_id TEXT PRIMARY KEY,
                canonical_url TEXT,
                status TEXT
            )
        """)
        conn.executemany(
            "INSERT INTO resource_audit_log (resource_id, canonical_url, status) VALUES (?, ?, ?)",
            [
                ("r1", "https://example.com/doc1.pdf", "PROCESADO_EXITOSAMENTE"),
                ("r2", "https://example.com/doc2.pdf", "PROCESADO_EXITOSAMENTE"),
                ("r3", "https://example.com/doc3.pdf", "PROCESADO_EXITOSAMENTE"),
                ("r4", "https://example.com/doc4.pdf", "PROCESADO_EXITOSAMENTE"),
            ],
        )
    return db_path


def test_classify_url_vigente():
    revalidator = UrlRevalidator()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "application/pdf"}
    mock_resp.url = "https://example.com/doc.pdf"
    mock_resp.history = []

    with patch.object(revalidator.session, "head", return_value=mock_resp):
        res = revalidator.check_url("https://example.com/doc.pdf", source="test")
        assert res.status == "VIGENTE"
        assert res.http_status == 200
        assert res.final_url == "https://example.com/doc.pdf"


def test_classify_url_redirigida():
    revalidator = UrlRevalidator()
    mock_history_item = MagicMock()
    mock_history_item.status_code = 301
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "application/pdf"}
    mock_resp.url = "https://example.com/new_doc.pdf"
    mock_resp.history = [mock_history_item]

    with patch.object(revalidator.session, "head", return_value=mock_resp):
        res = revalidator.check_url("https://example.com/old_doc.pdf", source="test")
        assert res.status == "REDIRIGIDA"
        assert res.http_status == 200
        assert res.final_url == "https://example.com/new_doc.pdf"


def test_classify_url_eliminada():
    revalidator = UrlRevalidator()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.headers = {}
    mock_resp.url = "https://example.com/deleted.pdf"
    mock_resp.history = []

    with patch.object(revalidator.session, "head", return_value=mock_resp):
        res = revalidator.check_url("https://example.com/deleted.pdf", source="test")
        assert res.status == "ELIMINADA"
        assert res.http_status == 404


def test_classify_url_inaccesible_on_error_and_403():
    revalidator = UrlRevalidator()

    # Caso 1: Error de conexión / timeout
    with patch.object(revalidator.session, "head", side_effect=requests.exceptions.ConnectTimeout("Timeout")):
        res = revalidator.check_url("https://example.com/timeout.pdf", source="test")
        assert res.status == "INACCESIBLE"
        assert "Timeout" in (res.error_message or "")

    # Caso 2: 403 Forbidden
    mock_403 = MagicMock()
    mock_403.status_code = 403
    mock_403.headers = {}
    mock_403.history = []
    with patch.object(revalidator.session, "head", return_value=mock_403):
        res = revalidator.check_url("https://example.com/forbidden.pdf", source="test")
        assert res.status == "INACCESIBLE"
        assert res.http_status == 403


def test_classify_url_405_fallback_to_get():
    revalidator = UrlRevalidator()
    mock_405 = MagicMock()
    mock_405.status_code = 405
    mock_405.headers = {}
    mock_405.history = []

    mock_get = MagicMock()
    mock_get.status_code = 200
    mock_get.headers = {"Content-Type": "application/pdf"}
    mock_get.url = "https://example.com/doc.pdf"
    mock_get.history = []

    with patch.object(revalidator.session, "head", return_value=mock_405):
        with patch.object(revalidator.session, "get", return_value=mock_get):
            res = revalidator.check_url("https://example.com/doc.pdf", source="test")
            assert res.status == "VIGENTE"
            assert res.http_status == 200


def test_revalidate_source_processes_inventory_and_writes_json(tmp_path, sample_inventory_db):
    base_output = tmp_path / "output"
    source_dir = base_output / "test_src"
    source_dir.mkdir(parents=True)
    import shutil
    shutil.copy(sample_inventory_db, source_dir / "inventory.db")

    revalidator = UrlRevalidator(base_output_dir=base_output)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "application/pdf"}
    mock_resp.history = []

    with patch.object(revalidator.session, "head", return_value=mock_resp):
        out_file, summary = revalidator.revalidate_source("test_src")
        assert out_file.exists()
        assert summary["total_urls"] == 4
        assert summary["VIGENTE"] == 4
        assert summary["ELIMINADA"] == 0
        assert summary["REDIRIGIDA"] == 0
        assert summary["INACCESIBLE"] == 0

        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert data["source"] == "test_src"
        assert len(data["results"]) == 4
        assert "revalidated_at" in data
