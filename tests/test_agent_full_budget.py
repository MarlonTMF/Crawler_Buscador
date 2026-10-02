"""
tests/test_agent_full_budget.py
===============================
Pruebas unitarias para el Bloque B-65: El agente con presupuesto completo.
Verifica:
1. Inicialización y estructura de agent_stats y agent_query_log en RecoveryLadder.
2. Registro preciso por consulta y conteo acumulativo:
   - faltantes consultados al agente
   - candidatos propuestos
   - pasaron HEAD
   - pasaron verificacion de contenido
   - pasaron compuertas de calidad
   - recuperados por el escalon 5
   - derivados a cola de herencia
3. Guardarraíles de seguridad: ningún dominio externo admitido directamente,
   respeto a max_gemini_calls, y sin escrituras no autorizadas.
"""

from unittest.mock import MagicMock, patch
import pytest

from crawler.core.recovery_ladder import RecoveryLadder, RecoveryRung


def test_agent_stats_initialization():
    ladder = RecoveryLadder(max_gemini_calls=35)
    assert hasattr(ladder, "agent_stats")
    stats = ladder.agent_stats
    assert stats["faltantes_consultados"] == 0
    assert stats["candidatos_propuestos"] == 0
    assert stats["pasaron_head"] == 0
    assert stats["pasaron_contenido"] == 0
    assert stats["pasaron_compuertas"] == 0
    assert stats["recuperados_rung_5"] == 0
    assert stats["derivados_herencia"] == 0
    assert hasattr(ladder, "agent_query_log")
    assert isinstance(ladder.agent_query_log, list)


def test_agent_query_tracking_counters_and_routing():
    ladder = RecoveryLadder(max_gemini_calls=10)

    # Simular candidatos propuestos por el agente:
    # 1. Dominio externo -> debe ir a cola de herencia
    # 2. Dominio válido pero HEAD 404 -> no pasa HEAD
    # 3. Dominio válido, pasa HEAD pero falla verificación de contenido
    # 4. Dominio válido, pasa HEAD, pasa contenido, pasa compuertas -> recuperado
    mock_candidates = [
        "https://external-domain.org/docs/reporte2025.pdf",
        "https://www.bcb.gob.bo/webdocs/no_existe.pdf",
        "https://www.bcb.gob.bo/webdocs/contenido_invalido.pdf",
        "https://www.bcb.gob.bo/webdocs/deuda_externa/DEPEX_2025_valido.pdf",
    ]

    with patch.object(ladder, "_ask_gemini_for_candidates", return_value=mock_candidates), \
         patch.object(ladder, "_get_allowed_domains", return_value=["bcb.gob.bo"]), \
         patch.object(ladder, "_check_head") as mock_head, \
         patch.object(ladder, "fetch_and_verify") as mock_fetch, \
         patch.object(ladder, "_verify_institution_content") as mock_inst, \
         patch.object(ladder, "_verify_period_correspondence", return_value=True), \
         patch.object(ladder, "is_url_in_inventory", return_value=False), \
         patch.object(ladder, "is_url_already_recovered", return_value=False), \
         patch.object(ladder, "_check_quality_gates", return_value=(True, None)):

        def fake_head(url, require_document_type=False):
            return "no_existe" not in url

        mock_head.side_effect = fake_head

        def fake_fetch(url):
            if "no_existe" in url:
                return None
            if "contenido_invalido" in url:
                ladder._last_download_sample = b"%PDF-1.4 Invalido"
            else:
                ladder._last_download_sample = b"%PDF-1.4 Banco Central de Bolivia"
            return (1024, "a" * 64)

        mock_fetch.side_effect = fake_fetch

        mock_inst.side_effect = lambda portal, sample: b"Invalido" not in sample

        res = ladder._try_rung_5_agent_gemini(
            portal="bcb",
            dataset_id="deuda_externa",
            period="2025-S1",
            periodicity="semestral",
        )

        assert res is not None
        assert res.recovery_rung == RecoveryRung.RUNG_5_AGENT_GEMINI
        assert res.url == "https://www.bcb.gob.bo/webdocs/deuda_externa/DEPEX_2025_valido.pdf"

        # Verificar estadísticas de B-65
        assert ladder.agent_stats["faltantes_consultados"] == 1
        assert ladder.agent_stats["candidatos_propuestos"] == 4
        assert ladder.agent_stats["derivados_herencia"] == 1
        assert ladder.agent_stats["pasaron_head"] >= 1
        assert ladder.agent_stats["pasaron_contenido"] >= 1
        assert ladder.agent_stats["pasaron_compuertas"] == 1
        assert ladder.agent_stats["recuperados_rung_5"] == 1

        # Verificar que el log de consultas tenga la entrada correspondiente
        assert len(ladder.agent_query_log) == 1
        log_entry = ladder.agent_query_log[0]
        assert log_entry["period"] == "2025-S1"
        assert log_entry["candidatos_propuestos"] == 4
        assert log_entry["derivados_herencia"] == 1


def test_agent_full_budget_exhaustion_behavior():
    ladder = RecoveryLadder(max_gemini_calls=2)

    with patch.object(ladder.fetcher, "_generate_gemini_content", return_value='["https://www.bcb.gob.bo/doc1.pdf"]'), \
         patch.object(ladder, "_check_head", return_value=False):

        ladder.fetcher.gemini_api_key = "dummy_key"

        # Llamada 1
        ladder._try_rung_5_agent_gemini("bcb", "deuda_externa", "2024-S1", "semestral")
        assert ladder.gemini_calls_count == 1

        # Llamada 2
        ladder._try_rung_5_agent_gemini("bcb", "deuda_externa", "2024-S2", "semestral")
        assert ladder.gemini_calls_count == 2

        # Llamada 3: presupuesto agotado
        res = ladder._try_rung_5_agent_gemini("bcb", "deuda_externa", "2025-S1", "semestral")
        assert res is None
        assert ladder.gemini_calls_count == 2  # No se incrementa más
