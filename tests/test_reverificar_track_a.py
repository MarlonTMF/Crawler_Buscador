"""
tests/test_reverificar_track_a.py
=================================
Pruebas para el script de re-verificación periódica de conectividad Track A
(Etapa E · B-25).

Criterios verificados:
1. Corrido dos veces seguidas sin cambios en la web no produce alertas (sin falsos positivos).
2. Contra una URL rota a propósito sí produce alerta (ambas comprobaciones).
3. Fuentes que ya estaban en error previo (410, disuelta) no generan falsa alarma de regresión.
4. Código de salida de CLI: 0 ante ausencia de regresiones, 1 ante regresiones detectadas.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import requests

from scripts.reverificar_track_a import (
    check_url_connectivity,
    verificar_catalogo_track_a,
    main as cli_main,
)


@pytest.fixture
def catalogo_mock(tmp_path: Path):
    """Crea un catálogo sintético con 4 fuentes: 3 en 200 y 1 en 410."""
    cat_file = tmp_path / "test_catalogo.json"
    data = [
        {
            "Fuente": "SRC_OK_1",
            "Institucion": "Institucion Estable 1",
            "Url_Original": "https://example.com/portal1",
            "Final_Url": "https://example.com/portal1",
            "HTTP_Status": "200",
        },
        {
            "Fuente": "SRC_OK_2",
            "Institucion": "Institucion Estable 2",
            "Url_Original": "https://example.com/portal2",
            "Final_Url": "https://example.com/portal2",
            "HTTP_Status": "200",
        },
        {
            "Fuente": "SRC_OK_3",
            "Institucion": "Institucion Estable 3",
            "Url_Original": "https://example.com/portal3",
            "Final_Url": "https://example.com/portal3",
            "HTTP_Status": "200",
        },
        {
            "Fuente": "SRC_EXCLUIDA",
            "Institucion": "Institucion Disuelta Previa",
            "Url_Original": "https://example.com/disuelta",
            "Final_Url": "https://example.com/disuelta",
            "HTTP_Status": "410",
        },
    ]
    cat_file.write_text(json.dumps(data), encoding="utf-8")
    return cat_file


def test_reverificar_sin_cambios_cero_alertas(catalogo_mock: Path):
    """Verifica que si todas las URLs en 200 responden 200, no hay ninguna alerta."""
    mock_resp_200 = MagicMock(status_code=200)

    with patch("requests.Session.head", return_value=mock_resp_200):
        reporte = verificar_catalogo_track_a(catalog_path=catalogo_mock, solo_200=True)

    assert reporte["total_verificados"] == 3
    assert reporte["total_ok"] == 3
    assert reporte["total_regresiones"] == 0
    assert len(reporte["regresiones"]) == 0


def test_reverificar_dos_veces_seguidas_idempotente(catalogo_mock: Path):
    """Criterio de aceptación 1: Corrido dos veces seguidas sin cambios no produce falsos positivos."""
    mock_resp_200 = MagicMock(status_code=200)

    with patch("requests.Session.head", return_value=mock_resp_200):
        # Primera corrida
        rep1 = verificar_catalogo_track_a(catalog_path=catalogo_mock, solo_200=True)
        # Segunda corrida inmediata sin cambios en la red
        rep2 = verificar_catalogo_track_a(catalog_path=catalogo_mock, solo_200=True)

    assert rep1["total_regresiones"] == 0
    assert rep2["total_regresiones"] == 0
    assert rep1["total_ok"] == rep2["total_ok"] == 3
    assert rep1["regresiones"] == rep2["regresiones"] == []


def test_reverificar_con_url_rota_produce_alerta(catalogo_mock: Path):
    """Criterio de aceptación 2: Contra una URL rota a propósito sí produce alerta de regresión."""
    def _mock_head(url, **kwargs):
        if "portal2" in url:
            # Simulamos que portal2 se cayó a 500
            return MagicMock(status_code=500)
        return MagicMock(status_code=200)

    with patch("requests.Session.head", side_effect=_mock_head):
        reporte = verificar_catalogo_track_a(catalog_path=catalogo_mock, solo_200=True)

    assert reporte["total_verificados"] == 3
    assert reporte["total_ok"] == 2
    assert reporte["total_regresiones"] == 1

    reg = reporte["regresiones"][0]
    assert reg["fuente"] == "SRC_OK_2"
    assert reg["estado_previo"] == "200"
    assert reg["estado_actual"] == 500
    assert reg["es_regresion"] is True


def test_reverificar_con_fallo_de_red_timeout(catalogo_mock: Path):
    """Verifica que un timeout de conexión se clasifique correctamente como regresión."""
    def _mock_head(url, **kwargs):
        if "portal3" in url:
            raise requests.exceptions.Timeout("Connection timed out")
        return MagicMock(status_code=200)

    with patch("requests.Session.head", side_effect=_mock_head):
        reporte = verificar_catalogo_track_a(catalog_path=catalogo_mock, solo_200=True)

    assert reporte["total_regresiones"] == 1
    reg = reporte["regresiones"][0]
    assert reg["fuente"] == "SRC_OK_3"
    assert reg["error"] == "Timeout"
    assert reg["es_regresion"] is True


def test_reverificar_url_previamente_rota_no_es_regresion(catalogo_mock: Path):
    """Verifica que si se evalúan todas las URLs (incluyendo 410 previa), la 410 no genera falsa regresión."""
    def _mock_head(url, **kwargs):
        if "disuelta" in url:
            return MagicMock(status_code=410)
        return MagicMock(status_code=200)

    with patch("requests.Session.head", side_effect=_mock_head):
        # solo_200=False evalúa todas
        reporte = verificar_catalogo_track_a(catalog_path=catalogo_mock, solo_200=False)

    assert reporte["total_verificados"] == 4
    # Aunque la fuente disuelta devuelve 410, como su estado previo ya era 410, no es una regresión
    assert reporte["total_regresiones"] == 0


def test_cli_exit_codes(catalogo_mock: Path, monkeypatch):
    """Verifica que la CLI salga con 0 sin regresiones y con 1 cuando hay regresión."""
    mock_resp_200 = MagicMock(status_code=200)

    # Caso 1: Todas OK -> exit 0
    with patch("requests.Session.head", return_value=mock_resp_200):
        monkeypatch.setattr("sys.argv", ["reverificar_track_a.py", "--catalogo", str(catalogo_mock)])
        with pytest.raises(SystemExit) as exc_info:
            cli_main()
        assert exc_info.value.code == 0

    # Caso 2: URL rota -> exit 1
    def _mock_head_failing(url, **kwargs):
        if "portal1" in url:
            return MagicMock(status_code=404)
        return MagicMock(status_code=200)

    with patch("requests.Session.head", side_effect=_mock_head_failing):
        monkeypatch.setattr("sys.argv", ["reverificar_track_a.py", "--catalogo", str(catalogo_mock)])
        with pytest.raises(SystemExit) as exc_info:
            cli_main()
        assert exc_info.value.code == 1
