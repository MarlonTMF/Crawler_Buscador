"""
tests/test_recovery_rung1.py
============================
Pruebas unitarias para el Escalón 1 real (B-61 / P-2).
Verifica que el escalón 1 siga el rastro de una URL conocida:
1. Seguir la redirección si la URL fue movida (301/302 hacia nueva URL con 200).
2. Si está eliminada (404), consultar el directorio superior e identificar archivo del período.
3. Probar variantes de la misma URL (mayúsculas, %20 / espacio, guion / guion bajo, extensión .PDF).
4. Caso negativo: devuelve None cuando la URL no existe ni tiene variantes/redirecciones válidas.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from crawler.core.recovery_ladder import RecoveryLadder, RecoveredPeriod, RecoveryRung


@pytest.fixture
def ladder(tmp_path):
    l = RecoveryLadder(base_output_dir=tmp_path)
    # Mockear compuertas de calidad para aislar la lógica del escalón
    l._check_quality_gates = MagicMock(return_value=(True, None))
    return l


def test_rung_1_seguir_redireccion(ladder):
    """Caso 1: Seguir redirección 301/302 hacia URL con 200."""
    known_url = "https://www.ine.gob.bo/index.php/descarga/pei_2020.pdf"
    target_url = "https://nube.ine.gob.bo/index.php/s/abc12345/download"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = target_url
    history_item = MagicMock()
    history_item.status_code = 302
    mock_resp.history = [history_item]

    with patch.object(ladder.fetcher.session, "head", return_value=mock_resp):
        with patch.object(ladder, "fetch_and_verify", side_effect=[None, (50000, "a" * 64)]):
            res = ladder._try_rung_1_known_url(
                portal="ine",
                dataset_id="planes_estrategicos",
                period="2020",
                periodicity="anual",
                known_url=known_url,
            )
            assert res is not None
            assert res.recovery_rung == RecoveryRung.RUNG_1_KNOWN_URL
            assert res.url == target_url
            assert res.file_size_bytes == 50000


def test_rung_1_directorio_superior_si_eliminada(ladder):
    """Caso 2: Si 404, consultar directorio superior y buscar archivo del mismo período."""
    known_url = "https://www.bcb.gob.bo/sites/default/files/documentos/memoria_2022.pdf"
    recovered_url = "https://www.bcb.gob.bo/sites/default/files/documentos/memoria_anual_2022_final.pdf"

    # HEAD de la URL original da 404
    mock_head_404 = MagicMock()
    mock_head_404.status_code = 404
    mock_head_404.history = []

    # GET del directorio superior devuelve HTML con enlace al archivo del período
    parent_html = """
    <html>
      <body>
        <h1>Listado de Documentos</h1>
        <a href="memoria_anual_2022_final.pdf">Memoria Anual 2022 Final</a>
        <a href="memoria_2021.pdf">Memoria 2021</a>
      </body>
    </html>
    """
    mock_get_dir = MagicMock()
    mock_get_dir.status_code = 200
    mock_get_dir.text = parent_html
    mock_get_dir.headers = {"Content-Type": "text/html"}

    def fake_head(url, *args, **kwargs):
        if url == known_url:
            return mock_head_404
        return MagicMock(status_code=200, history=[])

    def fake_fetch_and_verify(url):
        if url == recovered_url:
            return (75000, "b" * 64)
        return None

    with patch.object(ladder.fetcher.session, "head", side_effect=fake_head):
        with patch.object(ladder.fetcher.session, "get", return_value=mock_get_dir):
            with patch.object(ladder, "fetch_and_verify", side_effect=fake_fetch_and_verify):
                res = ladder._try_rung_1_known_url(
                    portal="bcb",
                    dataset_id="memorias_institucionales",
                    period="2022",
                    periodicity="anual",
                    known_url=known_url,
                )
                assert res is not None
                assert res.recovery_rung == RecoveryRung.RUNG_1_KNOWN_URL
                assert res.url == recovered_url
                assert res.file_size_bytes == 75000


def test_rung_1_variantes_codificacion_y_capitalizacion(ladder):
    """Caso 3: Probar variantes de la misma URL (guion/guion bajo, %20, mayúsculas)."""
    known_url = "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX-dic24.pdf"
    variant_url = "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20dic24.pdf"

    # URL original da 404
    mock_head_404 = MagicMock()
    mock_head_404.status_code = 404
    mock_head_404.history = []

    def fake_fetch_and_verify(url):
        if url == variant_url:
            return (123456, "c" * 64)
        return None

    with patch.object(ladder.fetcher.session, "head", return_value=mock_head_404):
        with patch.object(ladder.fetcher.session, "get", return_value=MagicMock(status_code=404)):
            with patch.object(ladder, "fetch_and_verify", side_effect=fake_fetch_and_verify):
                res = ladder._try_rung_1_known_url(
                    portal="bcb",
                    dataset_id="deuda_externa",
                    period="2024-S2",
                    periodicity="semestral",
                    known_url=known_url,
                )
                assert res is not None
                assert res.recovery_rung == RecoveryRung.RUNG_1_KNOWN_URL
                assert res.url == variant_url
                assert res.file_size_bytes == 123456


def test_rung_1_caso_negativo_devuelve_none(ladder):
    """Caso 4: Caso negativo sin variantes ni redirecciones devuelve None."""
    known_url = "https://www.ine.gob.bo/index.php/descarga/inexistente_1999.pdf"

    mock_head_404 = MagicMock()
    mock_head_404.status_code = 404
    mock_head_404.history = []

    with patch.object(ladder.fetcher.session, "head", return_value=mock_head_404):
        with patch.object(ladder.fetcher.session, "get", return_value=MagicMock(status_code=404)):
            with patch.object(ladder, "fetch_and_verify", return_value=None):
                res = ladder._try_rung_1_known_url(
                    portal="ine",
                    dataset_id="auditoria_interna",
                    period="1999",
                    periodicity="anual",
                    known_url=known_url,
                )
                assert res is None
