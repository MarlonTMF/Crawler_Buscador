"""
El calendario de una serie se arma solo con documentos de esa serie.

Caso real del 2 de octubre de 2026: 24 de los 37 faltantes detectados eran
artefactos. El calendario arrancaba en el documento más antiguo del dataset,
aunque no perteneciera a la serie: un reglamento de 2022 en la serie de
informes semestrales de deuda externa del BCB, un informe de auditoría de 2015
en los seguimientos trimestrales del POA de ASFI (que empiezan en 2020), una
página índice en las cuentas nacionales del INE.
"""

import sqlite3
from datetime import date

import pytest

from crawler.core.gap_detector import GapDetector


def _detector(filas):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE resource_audit_log (dataset_id TEXT, canonical_url TEXT, period_start TEXT, "
                 "period_end TEXT, published_at TEXT)")
    conn.executemany("INSERT INTO resource_audit_log VALUES (?,?,?,?,?)", filas)
    return GapDetector(conn=conn, reference_date=date(2026, 10, 2))


BCB = [
    ("deuda_externa", "https://deudaexternapublica.bcb.gob.bo/uploads/REGLAM_DEXT_2022.pdf", "2022-01-01", None, None),
    ("deuda_externa", "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20jun24.pdf", "2024-01-01", None, None),
    ("deuda_externa", "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20dic24.pdf", "2024-07-01", None, None),
    ("deuda_externa", "https://www.bcb.gob.bo/webdocs/informes_deudaexterna/DEPEX%20jun26.pdf", "2026-01-01", None, None),
    ("deuda_externa", "https://www.bcb.gob.bo/?q=informes-deuda-externa-publica", None, None, None),
]


def test_sin_patron_el_reglamento_ancla_la_serie_en_2022():
    rep = _detector(BCB).evaluate_dataset("deuda_externa", "semestral", 1)
    assert rep.first_observed_period == "2022-S1"
    assert "2023-S1" in rep.intermediate_gaps


def test_con_patron_la_serie_arranca_en_su_primer_informe():
    rep = _detector(BCB).evaluate_dataset("deuda_externa", "semestral", 1, series_pattern=r"DEPEX")
    assert rep.first_observed_period == "2024-S1"
    assert rep.intermediate_gaps == ["2025-S1", "2025-S2"]
    assert rep.excluded_from_calendar == 2  # el reglamento y la página índice


def test_las_paginas_sin_extension_documental_no_cuentan_nunca():
    filas = [
        ("cn", "https://www.ine.gob.bo/descarga/306/x/44535/cuadro-2013.xlsx", "2013-01-01", None, None),
        ("cn", "https://www.ine.gob.bo/descarga/306/x/44536/cuadro-2014.xlsx", "2014-01-01", None, None),
        ("cn", "https://www.ine.gob.bo/index.php/estadisticas-economicas/pib-y-cuentas-nacionales/", "2017-12-01", None, None),
    ]
    rep = _detector(filas).evaluate_dataset("cn", "anual", 1)
    assert rep.last_observed_period == "2014"
    assert rep.intermediate_gaps == []
    assert rep.excluded_from_calendar == 1


def test_documentos_dentro_de_zip_cuentan_como_documentales():
    filas = [
        ("bg", "https://www.asfi.gob.bo/files/2026-07/202509_BDR_EstadosFinancieros.zip#202509_BDR_EstadosFinancieros.xls",
         "2025-09-01", None, None),
        ("bg", "https://www.asfi.gob.bo/files/2026-07/202510_BDR_EstadosFinancieros.zip#202510_BDR_EstadosFinancieros.xls",
         "2025-10-01", None, None),
    ]
    rep = _detector(filas).evaluate_dataset("bg", "mensual", 2, series_pattern=r"_BDR_EstadosFinancieros")
    assert rep.first_observed_period == "2025-09" and rep.last_observed_period == "2025-10"
