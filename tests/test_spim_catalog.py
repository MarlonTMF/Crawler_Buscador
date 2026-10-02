"""Pruebas del lector del catálogo de SPIM (sin tocar el respaldo real)."""

from datetime import date

import pytest

from crawler.core.spim_catalog import (
    evaluate_currency,
    institution_for_url,
    normalize_periodicity,
    rows_to_series,
    snapshot_date,
)


@pytest.mark.parametrize("raw,esperado", [
    ("Mensual", "mensual"), ("mensual", "mensual"), ("Trimestral", "trimestral"),
    ("Semestral", "semestral"), ("Anual", "anual"), ("Diario", "diaria"),
    ("semanal", "semanal"), ("-", None), ("", None), (None, None), ("eventual", None),
])
def test_normaliza_frecuencia_de_texto_libre(raw, esperado):
    assert normalize_periodicity(raw) == esperado


@pytest.mark.parametrize("url,esperado", [
    ("https://www.bcb.gob.bo/webdocs/x.xlsx", "bcb"),
    ("https://deudaexternapublica.bcb.gob.bo/reporte", "bcb"),
    ("https://www.ine.gob.bo/index.php/descarga/1", "ine"),
    ("https://nube.ine.gob.bo/archivo.xlsx", "ine"),
    ("https://www.asfi.gob.bo/pb/x", "asfi"),
    ("https://estadisticas.minsalud.gob.bo/x", None),
    ("https://fakebcb.gob.bo.example.com/x", None),
    ("", None),
])
def test_institucion_por_dominio(url, esperado):
    assert institution_for_url(url) == esperado


def test_institucion_sale_del_dominio_y_no_del_id_source():
    """En SPIM, id_source=1 (BCB) agrupa series de otras instituciones."""
    sources = [{"id_source": 1, "short_name": "BCB"}]
    files = [
        {"id_file": 1, "id_source": 1, "code": "D1", "name": "Chagas Viviendas",
         "main_url": "https://estadisticas.minsalud.gob.bo/x", "publication_frequency": "-"},
        {"id_file": 2, "id_source": 1, "code": "D2", "name": "Tasas activas",
         "main_url": "https://www.bcb.gob.bo/tasas", "publication_frequency": "Semanal"},
    ]
    s = rows_to_series(sources, files)
    assert [x.institution for x in s] == [None, "bcb"]
    assert all(x.source_short_name == "BCB" for x in s)


def test_url_especifica_tiene_prioridad_y_vacios_se_ignoran():
    files = [{"id_file": 3, "id_source": 9, "code": "D3", "name": "x",
              "specific_url": "https://www.ine.gob.bo/a", "main_url": "https://www.asfi.gob.bo/b",
              "last_file_url": "-", "updated_to": "2026-05-31", "update_date": "2026-07-29"}]
    s = rows_to_series([], files)[0]
    assert s.institution == "ine"
    assert s.last_file_url is None
    assert s.updated_to == date(2026, 5, 31)
    assert snapshot_date([s]) == date(2026, 7, 29)


def _serie(periodicidad, hasta):
    return rows_to_series([], [{"id_file": 1, "id_source": 1, "code": "D", "name": "n",
                                "main_url": "https://www.bcb.gob.bo/x",
                                "publication_frequency": periodicidad, "updated_to": hasta}])[0]


REF = date(2026, 7, 29)


@pytest.mark.parametrize("periodicidad,hasta,estado", [
    ("Mensual", "2026-06-30", "AL_DIA"),
    ("Mensual", "2023-12-31", "ATRASADA"),
    ("Anual", "2025-12-31", "AL_DIA"),
    ("Anual", "2024-06-30", "ATRASADA"),
    ("Diario", "2026-07-24", "AL_DIA"),
    ("Diario", "2026-06-01", "ATRASADA"),
    ("Mensual", "2026-12-31", "FECHA_FUTURA"),
    ("-", "2026-06-30", "SIN_PERIODICIDAD"),
    ("Mensual", None, "SIN_FECHA"),
])
def test_vigencia_respecto_de_la_foto_del_respaldo(periodicidad, hasta, estado):
    assert evaluate_currency(_serie(periodicidad, hasta), REF).status == estado
