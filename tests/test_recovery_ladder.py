"""
Pruebas para B-54: Escalera de recuperación de períodos faltantes (regla de ver fallar el test antes del arreglo).
Verifica:
1. Orden estricto de los 4 escalones deterministas y detención en el primero exitoso.
2. Verificación rigurosa de bytes > 0 y hash SHA-256 en cada recuperación.
3. Descarte de URLs ya cosechadas en el inventario (O-1: una URL en inventory.db no es recuperación).
4. Descarte de rangos de años tipo YYYY-YYYY en coincidencia superficial (O-3).
5. Verificación de que las recuperaciones genuinas de BCB no existen en inventory.db.
"""

import sqlite3
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from crawler.core.recovery_ladder import (
    RecoveryLadder,
    RecoveryRung,
    RecoveredPeriod,
)


def test_recovery_ladder_rungs_order_and_early_stop():
    """Verifica el orden 1 -> 2 -> 3 -> 4 y la detención temprana en el primer éxito."""
    mock_fetcher = MagicMock()
    ladder = RecoveryLadder(fetcher=mock_fetcher)

    # Caso A: Escalón 1 responde -> no debe llamar a escalón 2, 3 ni 4
    with patch.object(ladder, "_try_rung_1_known_url") as m1, \
         patch.object(ladder, "_try_rung_2_series_template") as m2, \
         patch.object(ladder, "_try_rung_3_same_domain_alternate") as m3, \
         patch.object(ladder, "_try_rung_4_wayback_archive") as m4:

        m1.return_value = RecoveredPeriod(
            portal="bcb",
            dataset_id="test_ds",
            period="2024-S1",
            recovery_rung=1,
            rung_name="misma_url",
            url="https://example.com/known.pdf",
            file_size_bytes=1024,
            content_sha256="a" * 64,
            verified_at="2026-09-24T18:00:00Z",
        )

        res = ladder.recover_period("bcb", "test_ds", "2024-S1", periodicity="semestral")
        assert res is not None
        assert res.recovery_rung == 1
        m1.assert_called_once()
        m2.assert_not_called()
        m3.assert_not_called()
        m4.assert_not_called()

    # Caso B: Escalón 1 falla, Escalón 2 responde -> Escalón 3 y 4 no se llaman
    with patch.object(ladder, "_try_rung_1_known_url", return_value=None) as m1, \
         patch.object(ladder, "_try_rung_2_series_template") as m2, \
         patch.object(ladder, "_try_rung_3_same_domain_alternate") as m3, \
         patch.object(ladder, "_try_rung_4_wayback_archive") as m4:

        m2.return_value = RecoveredPeriod(
            portal="bcb",
            dataset_id="test_ds",
            period="2024-S1",
            recovery_rung=2,
            rung_name="plantilla_serie",
            url="https://example.com/template.pdf",
            file_size_bytes=2048,
            content_sha256="b" * 64,
            verified_at="2026-09-24T18:00:00Z",
        )

        res = ladder.recover_period("bcb", "test_ds", "2024-S1", periodicity="semestral")
        assert res is not None
        assert res.recovery_rung == 2
        m1.assert_called_once()
        m2.assert_called_once()
        m3.assert_not_called()
        m4.assert_not_called()

    # Caso C: Escalones 1 y 2 fallan, Escalón 3 responde -> Escalón 4 no se llama
    with patch.object(ladder, "_try_rung_1_known_url", return_value=None) as m1, \
         patch.object(ladder, "_try_rung_2_series_template", return_value=None) as m2, \
         patch.object(ladder, "_try_rung_3_same_domain_alternate") as m3, \
         patch.object(ladder, "_try_rung_4_wayback_archive") as m4:

        m3.return_value = RecoveredPeriod(
            portal="bcb",
            dataset_id="test_ds",
            period="2024-S1",
            recovery_rung=3,
            rung_name="ruta_alterna_dominio",
            url="https://example.com/alt.pdf",
            file_size_bytes=4096,
            content_sha256="c" * 64,
            verified_at="2026-09-24T18:00:00Z",
        )

        res = ladder.recover_period("bcb", "test_ds", "2024-S1", periodicity="semestral")
        assert res is not None
        assert res.recovery_rung == 3
        m1.assert_called_once()
        m2.assert_called_once()
        m3.assert_called_once()
        m4.assert_not_called()

    # Caso D: Escalones 1, 2 y 3 fallan, Escalón 4 (Wayback) responde
    with patch.object(ladder, "_try_rung_1_known_url", return_value=None) as m1, \
         patch.object(ladder, "_try_rung_2_series_template", return_value=None) as m2, \
         patch.object(ladder, "_try_rung_3_same_domain_alternate", return_value=None) as m3, \
         patch.object(ladder, "_try_rung_4_wayback_archive") as m4:

        m4.return_value = RecoveredPeriod(
            portal="bcb",
            dataset_id="test_ds",
            period="2024-S1",
            recovery_rung=4,
            rung_name="archivo_historico",
            url="http://web.archive.org/web/123/https://example.com/snap.pdf",
            file_size_bytes=8192,
            content_sha256="d" * 64,
            verified_at="2026-09-24T18:00:00Z",
        )

        res = ladder.recover_period("bcb", "test_ds", "2024-S1", periodicity="semestral")
        assert res is not None
        assert res.recovery_rung == 4
        m1.assert_called_once()
        m2.assert_called_once()
        m3.assert_called_once()
        m4.assert_called_once()


def test_recovery_ladder_hash_and_bytes_verification():
    """Verifica que un archivo recuperado valide tamaño > 0 y SHA-256."""
    ladder = RecoveryLadder()
    fake_content = b"PDF dummy content for unit testing SHA256 calculation"
    size, sha256 = ladder.verify_content_bytes(fake_content)

    assert size == len(fake_content)
    assert len(sha256) == 64
    assert isinstance(sha256, str)


def test_recovery_ladder_rejects_already_harvested_urls(tmp_path):
    """
    O-1: Verifica que cualquier candidato cuya canonical_url ya exista en
    resource_audit_log de inventory.db sea rechazado como recuperación.
    """
    portal_dir = tmp_path / "testportal"
    portal_dir.mkdir(parents=True)
    db_path = portal_dir / "inventory.db"

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE resource_audit_log (
            id INTEGER PRIMARY KEY,
            portal TEXT,
            dataset_id TEXT,
            canonical_url TEXT,
            period_start TEXT
        )
    """)
    harvested_url = "https://example.com/documento_ya_cosechado_2024.pdf"
    c.execute(
        "INSERT INTO resource_audit_log (portal, dataset_id, canonical_url, period_start) VALUES (?, ?, ?, ?)",
        ("testportal", "ds1", harvested_url, "2024-01-01"),
    )
    conn.commit()
    conn.close()

    ladder = RecoveryLadder(base_output_dir=tmp_path)

    # 1. Consulta directa al método is_url_in_inventory
    assert ladder.is_url_in_inventory("testportal", harvested_url) is True
    assert ladder.is_url_in_inventory("testportal", "https://example.com/nuevo_documento.pdf") is False

    # 2. Si un candidato es la URL ya cosechada, recover_period no la admite
    with patch.object(ladder, "_check_head", return_value=True), \
         patch.object(ladder, "fetch_and_verify", return_value=(1234, "e" * 64)):
        # Si Escalón 1 intentara proponer la URL cosechada, debe descartarse
        res = ladder._try_rung_1_known_url("testportal", "ds1", "2024", "anual")
        assert res is None, "Escalón 1 no debe admitir una URL ya cosechada en el inventario"


def test_recovery_ladder_rejects_year_ranges_in_rung_1(tmp_path):
    """
    O-3: Verifica que una coincidencia de año dentro de un rango '1988-2016'
    sea rechazada para el período '2016'.
    """
    portal_dir = tmp_path / "ine"
    portal_dir.mkdir(parents=True)
    db_path = portal_dir / "inventory.db"

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE resource_audit_log (
            id INTEGER PRIMARY KEY,
            portal TEXT,
            dataset_id TEXT,
            canonical_url TEXT,
            period_start TEXT
        )
    """)
    range_url = "https://www.ine.gob.bo/pib-anual-segun-tipo-de-gasto-1988-2016.xlsx"
    c.execute(
        "INSERT INTO resource_audit_log (portal, dataset_id, canonical_url, period_start) VALUES (?, ?, ?, ?)",
        ("ine", "cuentas_nacionales_pib", range_url, "1988-01-01"),
    )
    conn.commit()
    conn.close()

    ladder = RecoveryLadder(base_output_dir=tmp_path)

    with patch.object(ladder, "fetch_and_verify", return_value=(5000, "f" * 64)):
        res = ladder._try_rung_1_known_url("ine", "cuentas_nacionales_pib", "2016", "anual")
        assert res is None, "La URL con rango 1988-2016 no debe ser aceptada para el período 2016"


def test_recovery_ladder_real_recoveries_not_in_inventory():
    """
    O-1 / O-4: Verifica que las 3 recuperaciones reales del BCB por Escalón 2
    efectivamente NO existan previamente en output/bcb/inventory.db.
    """
    db_path = Path("output/bcb/inventory.db")
    assert db_path.exists(), "inventory.db de BCB debe existir"

    recovered_depex_urls = [
        "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20jun24.pdf",
        "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20dic24.pdf",
        "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20dic25.pdf",
    ]

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    for u in recovered_depex_urls:
        row = c.execute("SELECT 1 FROM resource_audit_log WHERE canonical_url = ?", (u,)).fetchone()
        assert row is None, f"La URL recuperada {u} ya existía en resource_audit_log del BCB!"
    conn.close()
