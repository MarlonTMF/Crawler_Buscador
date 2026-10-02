"""
tests/test_compuertas_calidad.py
================================
Pruebas para las dos compuertas de calidad de la Fase 5 (B-59):
1. Huella SHA-256 repetida: si el mismo content_sha256 ya se asignó a otro período
   del mismo dataset (en esta corrida o en inventory.db), se rechaza.
   - Caso real: cinco años de rendición/auditoría con la misma huella c599975b... (rechaza 4 de 5 o los 5).
2. Año contradictorio: si el nombre del archivo contiene un año de cuatro dígitos
   distinto del período buscado —y no hay otro año que coincida—, se rechaza.
   - Caso real INE: ine_escala_salarial_2026.pdf asignado a 2025 (debe rechazar).
   - Caso válido BCB: DEPEX dic25.pdf para 2025-S2 (debe admitir).
   - Caso con dos años donde uno coincide: informe_2024_publicado_2025.pdf para 2024 (debe admitir).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from crawler.core.recovery_ladder import RecoveryLadder, RecoveryRung


@pytest.fixture
def ladder(tmp_path):
    output_dir = tmp_path / "output"
    config_dir = tmp_path / "config"
    output_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    return RecoveryLadder(base_output_dir=output_dir, base_config_dir=config_dir)


def test_compuerta_huella_repetida_rechaza_anios_duplicados_en_misma_corrida(ladder):
    """
    Caso real P-3: cinco períodos (2013-2017) que devuelven el mismo hash SHA-256.
    La compuerta debe admitir el primero y rechazar los siguientes 4 (o rechazar los 5 si ya está en DB).
    """
    portal = "ine"
    dataset_id = "rendicion_cuentas"
    sha_identico = "c599975b9f7831d85608ad160db56782c599975b9f7831d85608ad160db56782"
    url_base = "https://www.ine.gob.bo/index.php/descarga/rendicion-publica-de-cuentas-{year}"

    # Evaluamos 2013: debe pasar (es el primero)
    ok_13, reason_13 = ladder._check_quality_gates(
        portal=portal,
        dataset_id=dataset_id,
        period="2013",
        url=url_base.format(year="2013"),
        content_sha256=sha_identico,
        source_rung=3,
    )
    assert ok_13 is True
    assert reason_13 is None

    # Evaluamos 2014, 2015, 2016, 2017 con el mismo hash: todos deben ser rechazados
    for y in ["2014", "2015", "2016", "2017"]:
        ok, reason = ladder._check_quality_gates(
            portal=portal,
            dataset_id=dataset_id,
            period=y,
            url=url_base.format(year=y),
            content_sha256=sha_identico,
            source_rung=3,
        )
        assert ok is False
        assert "huella_repetida" in reason
        assert "2013" in reason

    # Debe haber 4 rechazos registrados en rechazos_calidad
    assert len(ladder.rechazos_calidad) == 4
    for rechazo in ladder.rechazos_calidad:
        assert rechazo["portal"] == "ine"
        assert rechazo["dataset_id"] == "rendicion_cuentas"
        assert "huella_repetida" in rechazo["motivo"]


def test_compuerta_huella_repetida_rechaza_si_ya_existe_en_inventory_db(ladder):
    """Rechaza si el hash ya existe en inventory.db asignado a otro período."""
    portal = "ine"
    dataset_id = "rendicion_cuentas"
    sha_existente = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    with patch("sqlite3.connect") as mock_conn:
        cursor = MagicMock()
        cursor.fetchall.return_value = [("2018-01-01", "2018-12-31", "https://ine.gob.bo/doc.pdf")]
        mock_conn.return_value.__enter__.return_value.execute.return_value = cursor

        # Creamos el directorio simulado de inventory.db
        ine_dir = ladder.base_output_dir / portal
        ine_dir.mkdir(parents=True, exist_ok=True)
        (ine_dir / "inventory.db").touch()

        ok, reason = ladder._check_quality_gates(
            portal=portal,
            dataset_id=dataset_id,
            period="2013",
            url="https://www.ine.gob.bo/descarga/2013.pdf",
            content_sha256=sha_existente,
            source_rung=3,
        )
        assert ok is False
        assert "huella_repetida" in reason
        assert "inventory.db" in reason


def test_compuerta_ano_contradictorio_rechaza_ine_escala_salarial(ladder):
    """
    Caso real P-3: ine_escala_salarial_2026.pdf evaluado para período 2025.
    Contiene un año de 4 dígitos (2026) que contradice el período pedido (2025).
    """
    portal = "ine"
    dataset_id = "escala_salarial"
    period = "2025"
    url = "https://www.ine.gob.bo/archivos/ine_escala_salarial_2026.pdf"
    sha = "1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff"

    ok, reason = ladder._check_quality_gates(
        portal=portal,
        dataset_id=dataset_id,
        period=period,
        url=url,
        content_sha256=sha,
        source_rung=3,
    )
    assert ok is False
    assert "ano_contradictorio" in reason
    assert "2026" in reason
    assert len(ladder.rechazos_calidad) == 1
    assert ladder.rechazos_calidad[0]["motivo"] == reason


def test_compuerta_ano_contradictorio_admite_bcb_depex_dic25(ladder):
    """
    Caso válido real BCB: DEPEX dic25.pdf evaluado para 2025-S2.
    No contiene año de 4 dígitos contradictorio -> debe admitir sin rechazo.
    """
    portal = "bcb"
    dataset_id = "deuda_externa"
    period = "2025-S2"
    url = "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20dic25.pdf"
    sha = "7cba6779ec35a3e6e751b461b9261ea3415dbb366478a34f8e47c97900bf2a3d"

    ok, reason = ladder._check_quality_gates(
        portal=portal,
        dataset_id=dataset_id,
        period=period,
        url=url,
        content_sha256=sha,
        source_rung=2,
    )
    assert ok is True
    assert reason is None
    assert len(ladder.rechazos_calidad) == 0


def test_compuerta_ano_contradictorio_admite_si_al_menos_un_ano_coincide(ladder):
    """Si el archivo contiene dos años y uno coincide con el período pedido, se admite."""
    portal = "asfi"
    dataset_id = "informes"
    period = "2024"
    url = "https://www.asfi.gob.bo/docs/informe_gestion_2024_publicado_2025.pdf"
    sha = "aaaa0000bbbb1111cccc2222dddd3333eeee4444ffff5555aaaa6666bbbb7777"

    ok, reason = ladder._check_quality_gates(
        portal=portal,
        dataset_id=dataset_id,
        period=period,
        url=url,
        content_sha256=sha,
        source_rung=1,
    )
    assert ok is True
    assert reason is None
