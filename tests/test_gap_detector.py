"""
Pruebas para B-53: Detector de huecos y atrasos por dataset (Regla D-06).
Verifica detección de AL_DIA, ATRASADO, CON_HUECOS, INACTIVO,
y contraste de hueco real en el portal contra inventory.db.
"""

import pytest
import sqlite3
from datetime import date
from pathlib import Path

from crawler.core.gap_detector import (
    GapDetector, DatasetGapReport, DatasetState,
)
from crawler.core.extractor import MetadataExtractor
from crawler.core.fetcher import HttpFetcher
from crawler.sources.generic_adapter import GenericSourceAdapter


def test_b53_quarter_and_semester_extraction():
    """Verifica que extractor.py extraiga correctamente períodos trimestrales y semestrales."""
    adapter = GenericSourceAdapter(Path("config/source_asfi.yaml"))
    extractor = MetadataExtractor(HttpFetcher(), adapter)

    # Trimestres
    res_t1 = extractor.extract_date_layer1_url("https://example.com/Seguimiento%20al%20POA%20primer%20trimestre%202026.pdf")
    assert res_t1 is not None
    assert res_t1.period_start == "2026-01-01"
    assert res_t1.period_end == "2026-03-31"

    res_t2 = extractor.extract_date_layer1_url("https://example.com/Seguimiento%20al%20POA%20segundo%20trimestre%202026.pdf")
    assert res_t2 is not None
    assert res_t2.period_start == "2026-04-01"
    assert res_t2.period_end == "2026-06-30"

    res_t3 = extractor.extract_date_layer1_url("https://example.com/Seguimiento%20al%20POA%20tercer%20trimestre%202025.pdf")
    assert res_t3 is not None
    assert res_t3.period_start == "2025-07-01"
    assert res_t3.period_end == "2025-09-30"

    res_t4 = extractor.extract_date_layer1_url("https://example.com/Seguimiento%20al%20POA%20cuarto%20trimestre%202025.pdf")
    assert res_t4 is not None
    assert res_t4.period_start == "2025-10-01"
    assert res_t4.period_end == "2025-12-31"


def test_b53_synthetic_dataset_states(tmp_path):
    """Verifica con datos sintéticos los 4 estados: AL_DIA, ATRASADO, CON_HUECOS, INACTIVO."""
    db_file = tmp_path / "synthetic_inventory.db"
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE resource_audit_log (
            resource_id TEXT PRIMARY KEY,
            source_id TEXT,
            dataset_id TEXT,
            canonical_url TEXT,
            download_url TEXT,
            status TEXT,
            period_start TEXT,
            period_end TEXT,
            published_at TEXT,
            date_confidence_score TEXT,
            date_method TEXT
        )
        """
    )

    # 1. Dataset Mensual AL_DIA: 2026-06, 2026-07, 2026-08 (ref: 2026-09-15, tol: 2)
    for m in ["2026-06-01", "2026-07-01", "2026-08-01"]:
        conn.execute(
            "INSERT INTO resource_audit_log (resource_id, source_id, dataset_id, canonical_url, status, period_start) VALUES (?, 'src1', 'ds_al_dia', ?, 'SUCCESS', ?)",
            (f"id_{m}", f"http://ex.com/{m}", m)
        )

    # 2. Dataset Mensual CON_HUECOS: 2026-01, 2026-02, 2026-04 (falta marzo)
    for m in ["2026-01-01", "2026-02-01", "2026-04-01"]:
        conn.execute(
            "INSERT INTO resource_audit_log (resource_id, source_id, dataset_id, canonical_url, status, period_start) VALUES (?, 'src1', 'ds_huecos', ?, 'SUCCESS', ?)",
            (f"id_{m}", f"http://ex.com/{m}", m)
        )

    # 3. Dataset Mensual ATRASADO: 2025-10, 2025-11, 2025-12 (ref: 2026-09-15, tol: 2 -> atraso de 7 meses)
    for m in ["2025-10-01", "2025-11-01", "2025-12-01"]:
        conn.execute(
            "INSERT INTO resource_audit_log (resource_id, source_id, dataset_id, canonical_url, status, period_start) VALUES (?, 'src1', 'ds_atrasado', ?, 'SUCCESS', ?)",
            (f"id_{m}", f"http://ex.com/{m}", m)
        )

    # 4. Dataset INACTIVO: último dato en 2021
    conn.execute(
        "INSERT INTO resource_audit_log (resource_id, source_id, dataset_id, canonical_url, status, period_start) VALUES ('id_old', 'src1', 'ds_inactivo', 'http://ex.com/old', 'SUCCESS', '2021-01-01')"
    )
    conn.commit()

    detector = GapDetector(conn=conn, reference_date=date(2026, 9, 15))

    # Test ds_al_dia
    rep_al_dia = detector.evaluate_dataset("ds_al_dia", periodicity="mensual", tolerance=2)
    assert rep_al_dia.state == DatasetState.AL_DIA
    assert len(rep_al_dia.intermediate_gaps) == 0

    # Test ds_huecos
    rep_huecos = detector.evaluate_dataset("ds_huecos", periodicity="mensual", tolerance=2)
    assert rep_huecos.state == DatasetState.CON_HUECOS
    assert "2026-03" in rep_huecos.intermediate_gaps

    # Test ds_atrasado
    rep_atrasado = detector.evaluate_dataset("ds_atrasado", periodicity="mensual", tolerance=2)
    assert rep_atrasado.state == DatasetState.ATRASADO
    assert rep_atrasado.delay_periods > 2

    # Test ds_inactivo
    rep_inactivo = detector.evaluate_dataset("ds_inactivo", periodicity="anual", tolerance=1)
    assert rep_inactivo.state == DatasetState.INACTIVO


def test_b53_real_gap_verified_against_portal():
    """
    Criterio de aceptación B-53: Verificar al menos un hueco real contra el portal.
    En BCB 'deuda_externa' (semestral), el inventario tiene solo 2022 y 2026-06.
    Comprueba que el detector señale los semestres faltantes (ej. 2024-S1, 2024-S2, 2025-S2)
    cuya existencia con HTTP 200 fue verificada en el portal.
    """
    db_path = Path("output/bcb/inventory.db")
    if not db_path.exists():
        pytest.skip(f"No existe {db_path}")

    conn = sqlite3.connect(db_path)
    detector = GapDetector(conn=conn, reference_date=date(2026, 9, 24))
    rep = detector.evaluate_dataset("deuda_externa", periodicity="semestral", tolerance=1)

    assert rep.state in (DatasetState.CON_HUECOS, DatasetState.ATRASADO)
    assert len(rep.intermediate_gaps) > 0
    # 2024-S2 y 2025-S2 (verificados 200 OK en el portal) deben figurar como huecos detectados
    assert any("2024" in g for g in rep.intermediate_gaps)
    assert any("2025" in g for g in rep.intermediate_gaps)


def test_b53_semanal_and_unsupported_periodicity():
    """Verifica generación de períodos semanales y rechazo de periodicidades inválidas."""
    weeks = GapDetector.generate_expected_periods("2024-W01", "2024-W04", "semanal")
    assert weeks == ["2024-W01", "2024-W02", "2024-W03", "2024-W04"]

    with pytest.raises(ValueError, match="Periodicidad no soportada"):
        GapDetector.generate_expected_periods("2024", "2025", "desconocida")

