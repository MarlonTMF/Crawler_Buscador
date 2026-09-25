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
    if not db_path.exists():
        pytest.skip("Requiere output/bcb/inventory.db (datos locales no versionados)")

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


def test_recovery_ladder_rung_5_agent_called_when_rungs_1_to_4_fail():
    """B-54b: Verifica que el Escalón 5 (Agente Gemini) se invoque cuando fallan los escalones 1 a 4."""
    ladder = RecoveryLadder()
    with patch.object(ladder, "_try_rung_1_known_url", return_value=None), \
         patch.object(ladder, "_try_rung_2_series_template", return_value=None), \
         patch.object(ladder, "_try_rung_3_same_domain_alternate", return_value=None), \
         patch.object(ladder, "_try_rung_4_wayback_archive", return_value=None), \
         patch.object(ladder, "_try_rung_5_agent_gemini") as m5:

        m5.return_value = RecoveredPeriod(
            portal="bcb",
            dataset_id="test_ds",
            period="2023-S1",
            recovery_rung=5,
            rung_name="agente_gemini",
            url="https://www.bcb.gob.bo/docs/deuda_2023_s1.pdf",
            file_size_bytes=1024,
            content_sha256="e" * 64,
            verified_at="2026-09-24T20:00:00Z",
            metadata={"source_rung": 5, "method": "gemini_agent_helper"},
        )

        res = ladder.recover_period("bcb", "test_ds", "2023-S1", periodicity="semestral")
        assert res is not None
        assert res.recovery_rung == 5
        assert res.rung_name == "agente_gemini"
        m5.assert_called_once()


def test_recovery_ladder_rung_5_never_called_if_deterministic_rung_succeeds():
    """B-54b: El agente NUNCA se invoca si algún escalón determinista (1-4) tiene éxito."""
    ladder = RecoveryLadder()
    with patch.object(ladder, "_try_rung_1_known_url", return_value=None), \
         patch.object(ladder, "_try_rung_2_series_template") as m2, \
         patch.object(ladder, "_try_rung_5_agent_gemini") as m5:

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
        m5.assert_not_called()


def test_recovery_ladder_rung_5_rejects_candidate_if_head_or_content_fails(tmp_path):
    """
    B-54b: Toda propuesta del agente pasa por HEAD (D-17) y verificación de contenido (D-01).
    Si HEAD o el contenido institucional fallan, se descarta.
    """
    ladder = RecoveryLadder(base_output_dir=tmp_path)

    # 1. HEAD falla
    with patch.object(ladder, "_ask_gemini_for_candidates", return_value=["https://www.bcb.gob.bo/fake.pdf"]), \
         patch.object(ladder, "_check_head", return_value=False):
        res = ladder._try_rung_5_agent_gemini("bcb", "deuda_externa", "2023-S1", "semestral")
        assert res is None

    # 2. HEAD pasa pero verificación de contenido (D-01) falla
    with patch.object(ladder, "_ask_gemini_for_candidates", return_value=["https://www.bcb.gob.bo/wrong.pdf"]), \
         patch.object(ladder, "_check_head", return_value=True), \
         patch.object(ladder, "fetch_and_verify", return_value=(2048, "a" * 64)), \
         patch.object(ladder, "_verify_institution_content", return_value=False):
        res = ladder._try_rung_5_agent_gemini("bcb", "deuda_externa", "2023-S1", "semestral")
        assert res is None


def test_recovery_ladder_rung_5_rejects_different_domain_without_inheritance(tmp_path):
    """
    B-54b Regla 4: Cambio de dominio institucional nunca es automático (va a B-55).
    Si Gemini propone un dominio no autorizado en la configuración, se descarta.
    """
    ladder = RecoveryLadder(base_output_dir=tmp_path)
    with patch.object(ladder, "_ask_gemini_for_candidates", return_value=["https://bcp.org/deuda.pdf"]), \
         patch.object(ladder, "_check_head", return_value=True):
        res = ladder._try_rung_5_agent_gemini("bcb", "deuda_externa", "2023-S1", "semestral")
        assert res is None


def test_recovery_ladder_rung_5_call_limit_and_budget():
    """
    B-54b Regla 5: Tope de llamadas por corrida registrado.
    No debe exceder max_gemini_calls. No debe depender del .env local (H-6).
    """
    ladder = RecoveryLadder(max_gemini_calls=2)
    ladder.fetcher.gemini_api_key = "dummy_test_key"
    assert ladder.gemini_calls_count == 0
    with patch.object(ladder.fetcher, "_generate_gemini_content", return_value='["https://www.bcb.gob.bo/p1.pdf"]'), \
         patch.object(ladder, "_check_head", return_value=False):
        ladder._try_rung_5_agent_gemini("bcb", "deuda_externa", "2023-S1", "semestral")
        ladder._try_rung_5_agent_gemini("bcb", "deuda_externa", "2023-S2", "semestral")
        assert ladder.gemini_calls_count == 2
        # La 3ra llamada no debe consultar a Gemini por agotar el tope
        ladder._try_rung_5_agent_gemini("bcb", "deuda_externa", "2022-S2", "semestral")
        assert ladder.gemini_calls_count == 2


def test_recovery_ladder_rung_5_rejects_non_documentary_content_type(tmp_path):
    """
    B-54b Regla 2 (H-1 / H-2): Toda propuesta pasa por HEAD con status 200 y TIPO DOCUMENTAL (D-17).
    Rechaza explícitamente páginas HTML (text/html) o sin extensión documental.
    """
    ladder = RecoveryLadder(base_output_dir=tmp_path)
    ladder.fetcher.gemini_api_key = "dummy_test_key"

    # Caso A: Retorna text/html en HEAD
    with patch.object(ladder, "_ask_gemini_for_candidates", return_value=["https://www.ine.gob.bo/transparencia/"]), \
         patch.object(ladder, "_check_head", return_value=False):
        res = ladder._try_rung_5_agent_gemini("ine", "auditoria_interna", "2015", "anual")
        assert res is None, "Una página HTML debe ser rechazada por no ser tipo documental"

    # Caso B: _is_documentary_resource rechaza text/html
    assert ladder.is_documentary_resource("text/html; charset=UTF-8", "https://www.ine.gob.bo/page/") is False
    assert ladder.is_documentary_resource("application/pdf", "https://www.ine.gob.bo/doc.pdf") is True


def test_recovery_ladder_rung_5_rejects_candidate_without_period_correspondence(tmp_path):
    """
    B-54b (H-3): El candidato debe corresponder inequívocamente al período buscado.
    Si la URL o el contenido no hacen referencia al año/período, se descarta.
    """
    ladder = RecoveryLadder(base_output_dir=tmp_path)
    ladder.fetcher.gemini_api_key = "dummy_test_key"

    # Candidato de portal que habla de otro año o sin año
    with patch.object(ladder, "_ask_gemini_for_candidates", return_value=["https://www.ine.gob.bo/docs/general.pdf"]), \
         patch.object(ladder, "_check_head", return_value=True), \
         patch.object(ladder, "fetch_and_verify", return_value=(50000, "a" * 64)), \
         patch.object(ladder, "_verify_institution_content", return_value=True), \
         patch.object(ladder, "_verify_period_correspondence", return_value=False):
        res = ladder._try_rung_5_agent_gemini("ine", "cuentas_nacionales_pib", "2016", "anual")
        assert res is None, "Un candidato que no corresponde al período 2016 debe ser rechazado"


def test_recovery_ladder_verify_institution_content_rejects_substring_ine_in_words():
    """
    B-54b (H-4): D-01 no debe validar falsos positivos por subcadenas como 'ine' en 'linea' o 'determine'.
    Debe requerir coincidencia como palabra completa (\b).
    """
    ladder = RecoveryLadder()
    fake_content = b"Esta pagina en linea determine el flujo de informacion gubernamental"
    assert ladder._verify_institution_content("ine", fake_content) is False

    valid_content = b"Instituto Nacional de Estadistica del Estado Plurinacional de Bolivia - Cuentas Nacionales"
    assert ladder._verify_institution_content("ine", valid_content) is True


def test_recovery_ladder_rung_5_persists_external_domain_for_b55_inheritance(tmp_path):
    """
    B-54b Regla 4 & O-1: Candidatos de dominios externos sugeridos por Gemini deben
    ser persistidos en la cola de herencia para B-55 con su evidencia.
    """
    ladder = RecoveryLadder(base_output_dir=tmp_path)
    ladder.fetcher.gemini_api_key = "dummy_test_key"
    with patch.object(ladder, "_ask_gemini_for_candidates", return_value=["https://bcp.org/deuda_externa_2023.pdf"]):
        res = ladder._try_rung_5_agent_gemini("bcb", "deuda_externa", "2023-S1", "semestral")
        assert res is None
        assert len(ladder.inheritance_candidates) >= 1
        cand = ladder.inheritance_candidates[0]
        assert cand["portal"] == "bcb"
        assert cand["proposed_domain"] == "bcp.org"
        assert cand["proposed_url"] == "https://bcp.org/deuda_externa_2023.pdf"


def test_recovery_ladder_does_not_repeat_url_in_same_run():
    """
    B-54b (H-3): Una misma URL no puede ser admitida para dos períodos distintos en la misma corrida.
    """
    ladder = RecoveryLadder()
    ladder._recovered_urls.add("https://www.ine.gob.bo/docs/reporte.pdf")
    assert ladder.is_url_already_recovered("https://www.ine.gob.bo/docs/reporte.pdf") is True

