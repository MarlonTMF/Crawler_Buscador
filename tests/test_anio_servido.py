"""
Regresión: el año se comprueba sobre el archivo que entrega el servidor.

Caso real del 2 de octubre de 2026. El portal del INE entrega cada archivo
según un identificador numérico e ignora el nombre que lo acompaña en la URL.
El escalón 3 armaba candidatos escribiendo el año buscado en ese nombre, el
servidor devolvía el documento del identificador —de otro año— y la compuerta
de año lo aprobaba porque revisaba la URL construida por el propio sistema.

Las ocho recuperaciones falsas de esa corrida declaraban en Content-Disposition
un año distinto del buscado. Estas pruebas reproducen tres de ellas.
"""

from unittest.mock import MagicMock

import pytest

from crawler.core.recovery_ladder import RecoveryLadder, _served_filename


@pytest.fixture
def ladder(tmp_path):
    (tmp_path / "output").mkdir()
    (tmp_path / "config").mkdir()
    return RecoveryLadder(base_output_dir=tmp_path / "output", base_config_dir=tmp_path / "config")


def _respuesta(url_final: str, content_disposition: str | None, cuerpo: bytes = b"%PDF-1.7 contenido"):
    r = MagicMock()
    r.status_code = 200
    r.url = url_final
    headers = {"content-type": "application/pdf"}
    if content_disposition is not None:
        headers["content-disposition"] = content_disposition
    r.headers = headers
    r.iter_content = lambda chunk_size: [cuerpo]
    return r


# ── extracción del nombre servido ──────────────────────────────────────────

def test_nombre_servido_desde_content_disposition():
    r = _respuesta("https://www.ine.gob.bo/x/76983/pedido-2017.pdf",
                   'attachment; filename="Resumen INF UAI N\xb0 004-2026.pdf"')
    assert _served_filename(r) == "Resumen INF UAI N\xb0 004-2026.pdf"


def test_nombre_servido_en_formato_rfc5987():
    r = _respuesta("https://x/descarga", "attachment; filename*=UTF-8''ESCALA%20SALARIAL%202026.pdf")
    assert _served_filename(r) == "ESCALA SALARIAL 2026.pdf"


def test_sin_content_disposition_usa_la_url_final_tras_redirecciones():
    r = _respuesta("https://nube.ine.gob.bo/archivos/MATRIZ%20(2012).xlsx", None)
    assert _served_filename(r) == "MATRIZ (2012).xlsx"


# ── la compuerta usa lo servido, no lo pedido ──────────────────────────────

@pytest.mark.parametrize("periodo,url_pedida,cd_servido", [
    ("2016",
     "https://www.ine.gob.bo/index.php/descarga/778/informes-auditoria-interna-2016/73742/resumen-inf-uai-n-004-2016.pdf",
     'attachment; filename="Resumen INF UAI N 004-2026.pdf"'),
    ("2025",
     "https://www.ine.gob.bo/index.php/descarga/765/escala-salarial/74533/ine-escala-salarial-2025.pdf",
     'attachment; filename="ESCALA SALARIAL 2026.pdf"'),
    ("2016",
     "https://www.ine.gob.bo/index.php/descarga/406/matrices/44599/matriz-insumo-producto2016.xlsx",
     'attachment; filename="MATRIZ DE INSUMO PRODUCTO (EN MILES DE BOLIVIANOS)(2012).xlsx"'),
])
def test_rechaza_cuando_el_servidor_entrega_otro_anio(ladder, periodo, url_pedida, cd_servido):
    ladder._session = MagicMock()
    ladder._session.get.return_value = _respuesta(url_pedida, cd_servido)

    res = ladder.fetch_and_verify(url_pedida)
    assert res is not None, "la descarga en sí es válida"
    _, sha = res

    ok, motivo = ladder._check_quality_gates("ine", "auditoria_interna", periodo, url_pedida, sha, 3)
    assert ok is False
    assert motivo.startswith("ano_servido_contradictorio")


def test_admite_cuando_el_servidor_confirma_el_anio(ladder):
    url = "https://www.ine.gob.bo/index.php/descarga/1/escala/2/escala-2026.pdf"
    ladder._session = MagicMock()
    ladder._session.get.return_value = _respuesta(url, 'attachment; filename="ESCALA SALARIAL 2026.pdf"')
    _, sha = ladder.fetch_and_verify(url)
    ok, motivo = ladder._check_quality_gates("ine", "escala_salarial", "2026", url, sha, 3)
    assert ok is True and motivo is None


def test_admite_caso_bcb_sin_anio_de_cuatro_digitos(ladder):
    """DEPEX dic25.pdf: servidor estático, sin Content-Disposition y sin año de cuatro dígitos."""
    url = "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20dic25.pdf"
    ladder._session = MagicMock()
    ladder._session.get.return_value = _respuesta(url, None)
    _, sha = ladder.fetch_and_verify(url)
    ok, motivo = ladder._check_quality_gates("bcb", "deuda_externa", "2025-S2", url, sha, 2)
    assert ok is True and motivo is None
