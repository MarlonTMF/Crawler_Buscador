"""
tests/test_file_relocation_ladder.py
====================================
Batería de pruebas para la resolución de archivos reubicados y herencia cross-domain:
1. Seguimiento de redirecciones HTTP (301/302) en Escalón 1.
2. Traducción automática a dominios y rutas sucesoras (moved_urls.json) en Escalón 1.
3. Generación heurística dinámica de rutas alternas en Escalón 3 (no-BCB).
4. Consulta universal Wayback Availability en Escalón 4.
5. Aceptación controlada de dominios sucesores autorizados en Escalón 5.
6. Rechazo estricto de dominios no autorizados (encolado para B-55).
7. Verificación de contenido institucional (D-01) y salvaguarda documental (D-14).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import json
import pytest

from crawler.core.recovery_ladder import RecoveryLadder, RecoveryRung, RecoveredPeriod


@pytest.fixture
def ladder(tmp_path):
    ladder_obj = RecoveryLadder(base_output_dir=tmp_path / "output", base_config_dir=tmp_path / "config")
    ladder_obj._get_allowed_domains = MagicMock(return_value=["spvs.gob.bo", "www.spvs.gob.bo"])
    return ladder_obj


def test_escalon_1_follows_redirect_to_new_location(ladder):
    """Escalón 1 sigue redirecciones HTTP cuando el archivo se movió a una nueva URL autorizada."""
    cand_url = "https://www.spvs.gob.bo/docs/memoria_2020.pdf"
    new_url = "https://www.asfi.gob.bo/docs/spvs_memoria_2020.pdf"

    with patch.object(ladder, "is_url_in_inventory", return_value=False), \
         patch.object(ladder, "is_url_already_recovered", return_value=False), \
         patch.object(ladder, "fetch_and_verify", side_effect=[None, (2048, "a" * 64)]), \
         patch.object(ladder, "_verify_institution_content", return_value=True), \
         patch.object(ladder.relocation_manager, "follow_redirect", return_value={
             "original_url": cand_url,
             "final_url": new_url,
             "redirected": True,
             "is_authorized": True,
             "status_code": 200,
         }):

        # Simulamos que candidate_urls en Escalón 1 devuelve cand_url
        with patch("sqlite3.connect") as mock_conn:
            cursor = MagicMock()
            cursor.execute.return_value = cursor
            cursor.fetchall.return_value = [(cand_url,)]
            mock_conn.return_value.cursor.return_value = cursor
            (ladder.base_output_dir / "spvs").mkdir(parents=True, exist_ok=True)
            (ladder.base_output_dir / "spvs" / "inventory.db").touch()

            rec = ladder._try_rung_1_known_url("spvs", "memorias", "2020", "anual")
            assert rec is not None
            assert rec.url == new_url
            assert rec.recovery_rung == RecoveryRung.RUNG_1_KNOWN_URL
            assert rec.rung_name == "misma_url_redireccion"
            assert rec.metadata["redirected_from"] == cand_url


def test_escalon_1_translates_to_successor_domain(ladder):
    """Escalón 1 traduce la URL al dominio sucesor cuando la URL original devuelve 404."""
    old_url = "https://www.spvs.gob.bo/archivos/memoria_2019.pdf"
    succ_url = "https://www.asfi.gob.bo/docs/spvs/memoria_2019.pdf"

    with patch.object(ladder, "is_url_in_inventory", return_value=False), \
         patch.object(ladder, "is_url_already_recovered", return_value=False), \
         patch.object(ladder, "fetch_and_verify", side_effect=[None, (4096, "b" * 64)]), \
         patch.object(ladder, "_check_head", return_value=True), \
         patch.object(ladder, "_verify_institution_content", return_value=True), \
         patch.object(ladder.relocation_manager, "follow_redirect", return_value={"redirected": False}), \
         patch.object(ladder.relocation_manager, "translate_url_to_successor", return_value=[succ_url]):

        with patch("sqlite3.connect") as mock_conn:
            cursor = MagicMock()
            cursor.execute.return_value = cursor
            cursor.fetchall.return_value = [(old_url,)]
            mock_conn.return_value.cursor.return_value = cursor
            (ladder.base_output_dir / "spvs").mkdir(parents=True, exist_ok=True)
            (ladder.base_output_dir / "spvs" / "inventory.db").touch()

            rec = ladder._try_rung_1_known_url("spvs", "memorias", "2019", "anual")
            assert rec is not None
            assert rec.url == succ_url
            assert rec.rung_name == "misma_url_reubicada"
            assert rec.metadata["method"] == "known_url_successor_mapping"


def test_escalon_3_dynamic_path_variants_for_other_portals(ladder):
    """Escalón 3 genera variaciones de ruta heurísticas dinámicas para portales distintos a BCB."""
    portal = "aduana"
    dataset_id = "boletines"
    period = "2023"
    seed_url = "https://www.aduana.gob.bo/archivos/boletin_2023.pdf"
    variant_url = "https://www.aduana.gob.bo/docs/boletin_2023.pdf"

    with patch.object(ladder, "_build_template_urls", return_value=[seed_url]), \
         patch.object(ladder, "is_url_in_inventory", return_value=False), \
         patch.object(ladder, "is_url_already_recovered", return_value=False), \
         patch.object(ladder, "_check_head", return_value=True), \
         patch.object(ladder, "fetch_and_verify", return_value=(8192, "c" * 64)), \
         patch.object(ladder.relocation_manager, "generate_path_variants", return_value=[variant_url]):

        rec = ladder._try_rung_3_same_domain_alternate(portal, dataset_id, period, "anual")
        assert rec is not None
        assert rec.url == variant_url
        assert rec.recovery_rung == RecoveryRung.RUNG_3_SAME_DOMAIN_ALTERNATE
        assert rec.rung_name == "ruta_alterna_dominio"


def test_escalon_4_universal_wayback_query(ladder):
    """Escalón 4 consulta Wayback Availability API dinámicamente para cualquier portal."""
    portal = "senasag"
    dataset_id = "informes"
    period = "2021"
    target_url = "https://www.senasag.gob.bo/informes/2021.pdf"
    snap_url = "https://web.archive.org/web/20220101/https://www.senasag.gob.bo/informes/2021.pdf"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "archived_snapshots": {
            "closest": {
                "available": True,
                "status": "200",
                "url": snap_url,
                "timestamp": "20220101120000",
            }
        }
    }

    with patch.object(ladder, "_build_template_urls", return_value=[target_url]), \
         patch.object(ladder._session, "get", return_value=mock_resp), \
         patch.object(ladder, "fetch_and_verify", return_value=(10240, "d" * 64)):

        rec = ladder._try_rung_4_wayback_archive(portal, dataset_id, period, "anual")
        assert rec is not None
        assert rec.url == snap_url
        assert rec.recovery_rung == RecoveryRung.RUNG_4_WAYBACK_ARCHIVE
        assert rec.rung_name == "archivo_historico"


def test_escalon_5_routes_successor_domain_to_inheritance_queue(ladder):
    """P-6 (D-18): Escalón 5 deriva candidatos de dominio sucesor a la cola de herencia B-55 sin autoaceptación."""
    cand_url = "https://www.asfi.gob.bo/docs/spvs_memoria_2018.pdf"

    with patch.object(ladder, "_ask_gemini_for_candidates", return_value=[cand_url]), \
         patch.object(ladder, "_check_head", return_value=True), \
         patch.object(ladder, "fetch_and_verify", return_value=(5000, "e" * 64)), \
         patch.object(ladder, "_verify_institution_content", return_value=True), \
         patch.object(ladder, "_verify_period_correspondence", return_value=True), \
         patch.object(ladder, "is_url_in_inventory", return_value=False), \
         patch.object(ladder, "is_url_already_recovered", return_value=False):

        rec = ladder._try_rung_5_agent_gemini("spvs", "memorias", "2018", "anual")
        # Bajo P-6 no se autoacepta: debe ser None y pasar a la cola de herencia
        assert rec is None
        assert len(ladder.inheritance_candidates) == 1
        entry = ladder.inheritance_candidates[0]
        assert entry["proposed_url"] == cand_url
        assert "cola de herencia B-55" in entry["reason"]



def test_escalon_5_rejects_unauthorized_external_domain(ladder):
    """Escalón 5 descarta y encola para auditoría B-55 si el dominio externo no es sucesor autorizado."""
    unauthorized_url = "https://www.dominio-desconocido.com/memoria_2018.pdf"

    with patch.object(ladder, "_ask_gemini_for_candidates", return_value=[unauthorized_url]):
        rec = ladder._try_rung_5_agent_gemini("spvs", "memorias", "2018", "anual")
        assert rec is None
        assert len(ladder.inheritance_candidates) == 1
        entry = ladder.inheritance_candidates[0]
        assert entry["proposed_url"] == unauthorized_url
        assert entry["proposed_domain"] == "www.dominio-desconocido.com"


def test_escalon_5_rejects_html_content_under_d14(ladder):
    """Escalón 5 rechaza respuestas text/html bajo D-14 / H-1 incluso si responde 200 en dominio sucesor."""
    cand_url = "https://www.asfi.gob.bo/portal_error.html"

    with patch.object(ladder, "_ask_gemini_for_candidates", return_value=[cand_url]), \
         patch.object(ladder, "_check_head", return_value=False):  # HEAD rechaza por text/html

        rec = ladder._try_rung_5_agent_gemini("spvs", "memorias", "2018", "anual")
        assert rec is None


def test_escalon_5_rejects_mismatched_content_under_d01(ladder):
    """Escalón 5 rechaza el candidato si el contenido descargado no menciona a la institución (D-01)."""
    cand_url = "https://www.asfi.gob.bo/docs/otro_tema.pdf"

    with patch.object(ladder, "_ask_gemini_for_candidates", return_value=[cand_url]), \
         patch.object(ladder, "_check_head", return_value=True), \
         patch.object(ladder, "fetch_and_verify", return_value=(5000, "f" * 64)), \
         patch.object(ladder, "_verify_institution_content", return_value=False):  # Falla D-01

        rec = ladder._try_rung_5_agent_gemini("spvs", "memorias", "2018", "anual")
        assert rec is None
