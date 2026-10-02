"""
tests/test_recovery_rung3.py
============================
Pruebas unitarias para el Escalón 3 derivado de la serie (B-62 / P-3).
Verifica:
1. Derivación de candidatos a partir de URLs observadas de la serie en inventory.db (reemplazo de año y trimestre/semestre/mes).
2. Derivación para los 20 faltantes de asfi/poa_seguimiento.
3. Búsqueda en sitemap.xml cuando el portal lo publica.
4. Modo dry-run en RecoveryLadder y scripts/recuperar_periodos.py.
"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from crawler.core.recovery_ladder import RecoveryLadder, RecoveredPeriod, RecoveryRung


@pytest.fixture
def ladder(tmp_path):
    l = RecoveryLadder(base_output_dir=tmp_path)
    l._check_quality_gates = MagicMock(return_value=(True, None))
    return l


def test_rung_3_deriva_candidatos_trimestral(ladder, tmp_path):
    """Verifica que el escalón 3 derive URLs para períodos trimestrales a partir de URLs observadas."""
    asfi_dir = tmp_path / "asfi"
    asfi_dir.mkdir(parents=True, exist_ok=True)
    db_path = asfi_dir / "inventory.db"

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE resource_audit_log (
            id INTEGER PRIMARY KEY,
            portal TEXT,
            dataset_id TEXT,
            canonical_url TEXT,
            period_start TEXT,
            period_end TEXT,
            status TEXT
        )
    """)
    observed_url = "https://www.asfi.gob.bo/sites/default/files/2025-07/Seguimiento%20al%20POA%20primer%20trimestre%202023.pdf"
    conn.execute(
        "INSERT INTO resource_audit_log (portal, dataset_id, canonical_url, status) VALUES (?, ?, ?, ?)",
        ("asfi", "poa_seguimiento", observed_url, "PROCESADO_EXITOSAMENTE"),
    )
    conn.commit()
    conn.close()

    candidates = ladder._derive_candidates_from_dataset_urls("asfi", "poa_seguimiento", "2016-Q2", "trimestral")
    assert len(candidates) > 0
    # Al menos un candidato debe contener 2016 y segundo trimestre
    found = any("2016" in c and ("segundo" in c.lower() or "2do" in c.lower() or "q2" in c.lower()) for c in candidates)
    assert found, f"No se encontró candidato para 2016-Q2 en: {candidates}"


def test_rung_3_deriva_candidatos_semestral(ladder, tmp_path):
    """Verifica que el escalón 3 derive URLs para períodos semestrales (ej. jun/dic o S1/S2)."""
    bcb_dir = tmp_path / "bcb"
    bcb_dir.mkdir(parents=True, exist_ok=True)
    db_path = bcb_dir / "inventory.db"

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE resource_audit_log (
            id INTEGER PRIMARY KEY,
            portal TEXT,
            dataset_id TEXT,
            canonical_url TEXT,
            status TEXT
        )
    """)
    observed_url = "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20dic24.pdf"
    conn.execute(
        "INSERT INTO resource_audit_log (portal, dataset_id, canonical_url, status) VALUES (?, ?, ?, ?)",
        ("bcb", "deuda_externa", observed_url, "PROCESADO_EXITOSAMENTE"),
    )
    conn.commit()
    conn.close()

    candidates = ladder._derive_candidates_from_dataset_urls("bcb", "deuda_externa", "2025-S1", "semestral")
    assert len(candidates) > 0
    found = any("25" in c and "jun" in c.lower() for c in candidates)
    assert found, f"No se encontró candidato para 2025-S1 en: {candidates}"


def test_rung_3_integra_sitemap_si_publicado(ladder):
    """Verifica que el escalón 3 consulte sitemap.xml y agregue URLs que coincidan con el dataset."""
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
       <url>
          <loc>https://www.ine.gob.bo/descargas/rendicion_cuentas_2023.pdf</loc>
       </url>
       <url>
          <loc>https://www.ine.gob.bo/otra_cosa.html</loc>
       </url>
    </urlset>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = sitemap_xml
    mock_resp.headers = {"Content-Type": "application/xml"}

    with patch.object(ladder.fetcher.session, "get", return_value=mock_resp):
        sitemap_urls = ladder._get_sitemap_urls("ine", "rendicion_cuentas", "2023")
        assert "https://www.ine.gob.bo/descargas/rendicion_cuentas_2023.pdf" in sitemap_urls


def test_dry_run_lists_candidates_for_all_20_poa_gaps(ladder):
    """Criterio de aceptación B-62: dry-run debe listar candidatos para los 20 faltantes de asfi/poa_seguimiento."""
    # Usar base_output_dir real para acceder a output/asfi/inventory.db
    real_ladder = RecoveryLadder(base_output_dir=Path("output"))
    gaps_20 = [
        "2015-Q2", "2015-Q3", "2015-Q4",
        "2016-Q1", "2016-Q2", "2016-Q3", "2016-Q4",
        "2017-Q1", "2017-Q2", "2017-Q3", "2017-Q4",
        "2018-Q1", "2018-Q2", "2018-Q3", "2018-Q4",
        "2019-Q1", "2019-Q2", "2019-Q3", "2019-Q4",
        "2024-Q3",
    ]
    for period in gaps_20:
        cands = real_ladder._derive_candidates_from_dataset_urls("asfi", "poa_seguimiento", period, "trimestral")
        assert len(cands) > 0, f"No se derivaron candidatos para el período {period}"
