"""
tests/test_dataset_lifecycle.py
================================
Batería de pruebas unitarias para el ciclo de vida de datasets (B-56).
Valida las reglas de transición entre estados:
  VIGENTE, ATRASADO, MIGRADO, HISTORICO.
Criterio fundamental de B-56:
- El paso a HISTORICO nunca es automático por silencio: exige que la escalera
  de B-54 se haya agotado y quede registrado qué se intentó.
- El paso a MIGRADO exige herencia ACEPTADA (D-18 §6) o procedencia catalogada.
"""

from datetime import date
import json
from pathlib import Path
import pytest

from crawler.core.lifecycle import (
    DatasetLifecycleManager,
    DatasetLifecycleRecord,
    DatasetLifecycleState,
    TransitionRule,
)
from crawler.core.gap_detector import DatasetGapReport, DatasetState


def test_lifecycle_vigente_when_on_time():
    """Dataset al día dentro de tolerancia debe ser VIGENTE."""
    manager = DatasetLifecycleManager()
    gap_rep = DatasetGapReport(
        dataset_id="boletin_mensual",
        periodicity="mensual",
        tolerance=2,
        total_resources=12,
        first_observed_period="2025-01",
        last_observed_period="2026-08",
        delay_periods=1,
        state=DatasetState.AL_DIA,
    )
    rec = manager.evaluate_dataset_lifecycle(
        portal="asfi",
        dataset_id="boletin_mensual",
        gap_report=gap_rep,
    )
    assert rec.state == DatasetLifecycleState.VIGENTE
    assert rec.transition_rule == TransitionRule.VIG_AL_DIA
    assert rec.delay_periods == 1


def test_lifecycle_atrasado_when_delayed_and_ladder_not_exhausted():
    """
    Dataset con retraso superior a tolerancia pero sin escalera ejecutada o incompleta
    debe permanecer en ATRASADO, nunca pasar a HISTORICO.
    """
    manager = DatasetLifecycleManager()
    gap_rep = DatasetGapReport(
        dataset_id="deuda_externa",
        periodicity="semestral",
        tolerance=1,
        total_resources=5,
        first_observed_period="2020-S1",
        last_observed_period="2023-S2",
        delay_periods=4,
        state=DatasetState.ATRASADO,
    )
    # Sin intentos de recuperación
    rec = manager.evaluate_dataset_lifecycle(
        portal="bcb",
        dataset_id="deuda_externa",
        gap_report=gap_rep,
        recovery_attempts=[],
    )
    assert rec.state == DatasetLifecycleState.ATRASADO
    assert rec.transition_rule == TransitionRule.ATR_BUSQUEDA_PENDIENTE
    assert not rec.recovery_attempts_exhausted


def test_lifecycle_rejects_automatic_historico_by_silence():
    """
    Control negativo: Un dataset inactivo durante años (silencio prolongado)
    NUNCA puede transicionar a HISTORICO si no se agotó la escalera de B-54.
    """
    manager = DatasetLifecycleManager()
    gap_rep = DatasetGapReport(
        dataset_id="cuentas_nacionales_pib",
        periodicity="anual",
        tolerance=1,
        total_resources=20,
        first_observed_period="1988",
        last_observed_period="2017",
        delay_periods=9,
        state=DatasetState.INACTIVO,
    )
    # Solo se intentó escalón 1 y falló, pero NO se intentaron los demás
    partial_attempts = [
        {"rung": 1, "name": "Misma URL", "success": False, "reason": "HTTP 404"}
    ]
    rec = manager.evaluate_dataset_lifecycle(
        portal="ine",
        dataset_id="cuentas_nacionales_pib",
        gap_report=gap_rep,
        recovery_attempts=partial_attempts,
    )
    # Debe ser rechazado como HISTORICO y mantenerse como ATRASADO
    assert rec.state == DatasetLifecycleState.ATRASADO
    assert rec.state != DatasetLifecycleState.HISTORICO
    assert "no se han agotado todos los escalones" in rec.justification.lower()


def test_lifecycle_historico_when_ladder_fully_exhausted():
    """
    Transición justificada a HISTORICO: la escalera de B-54 se ejecutó y agotó
    todos sus escalones deterministas (1, 2, 3, 4) y agente sin hallar nuevos períodos.
    """
    manager = DatasetLifecycleManager()
    gap_rep = DatasetGapReport(
        dataset_id="cuentas_nacionales_pib",
        periodicity="anual",
        tolerance=1,
        total_resources=20,
        first_observed_period="1988",
        last_observed_period="2017",
        delay_periods=9,
        state=DatasetState.INACTIVO,
    )
    # Todos los escalones agotados
    exhausted_attempts = [
        {"rung": 1, "name": "Misma URL", "success": False, "tested_url": "https://ine.gob.bo/pib_2018.pdf"},
        {"rung": 2, "name": "Plantilla serie", "success": False, "tested_url": "https://ine.gob.bo/pib/2018.xlsx"},
        {"rung": 3, "name": "Ruta alterna dominio", "success": False, "tested_url": "https://ine.gob.bo/sitemap_search"},
        {"rung": 4, "name": "Wayback Machine", "success": False, "tested_url": "https://web.archive.org/web/*/ine.gob.bo/pib*"},
        {"rung": 5, "name": "Agente Gemini", "success": False, "tested_url": "gemini_exhausted"},
    ]
    rec = manager.evaluate_dataset_lifecycle(
        portal="ine",
        dataset_id="cuentas_nacionales_pib",
        gap_report=gap_rep,
        recovery_attempts=exhausted_attempts,
    )
    assert rec.state == DatasetLifecycleState.HISTORICO
    assert rec.transition_rule == TransitionRule.HIST_ESCALERA_AGOTADA
    assert rec.recovery_attempts_exhausted
    assert len(rec.recovery_attempts_log) == 5
    assert "archivado justificado" in rec.justification.lower()


def test_lifecycle_migrado_requires_accepted_inheritance_d18():
    """
    Bajo D-18 §6: solo una herencia ACEPTADA lleva un dataset a MIGRADO.
    Una propuesta en estado PROPUESTA o RECHAZADA no provoca migración.
    """
    manager = DatasetLifecycleManager()
    gap_rep = DatasetGapReport(
        dataset_id="boletines_historicos",
        periodicity="mensual",
        tolerance=1,
        total_resources=10,
        first_observed_period="2000-01",
        last_observed_period="2009-02",
        delay_periods=100,
        state=DatasetState.INACTIVO,
    )
    # Herencia solo propuesta, NO aceptada aún por una persona
    proposal_not_accepted = {
        "origen_portal": "sbef",
        "origen_dataset": "boletines_historicos",
        "destino_entidad": "ASFI",
        "status": "PROPUESTA",
    }
    rec = manager.evaluate_dataset_lifecycle(
        portal="sbef",
        dataset_id="boletines_historicos",
        gap_report=gap_rep,
        inheritance_proposals=[proposal_not_accepted],
    )
    assert rec.state != DatasetLifecycleState.MIGRADO

    # Herencia formalmente ACEPTADA por una persona bajo D-18 §5
    proposal_accepted = {
        "origen_portal": "sbef",
        "origen_dataset": "boletines_historicos",
        "destino_entidad": "ASFI",
        "status": "ACEPTADA",
        "evidencia": "Ley 393 / DS 29894",
    }
    rec_migrado = manager.evaluate_dataset_lifecycle(
        portal="sbef",
        dataset_id="boletines_historicos",
        gap_report=gap_rep,
        inheritance_proposals=[proposal_accepted],
    )
    assert rec_migrado.state == DatasetLifecycleState.MIGRADO
    assert rec_migrado.transition_rule == TransitionRule.MIG_D18_ACEPTADA
    assert rec_migrado.migration_reference is not None


def test_lifecycle_migrado_from_catalog_precedents():
    """
    Fuentes de procedencia histórica catalogadas (SPVS, SUPTRANS)
    se reconocen automáticamente como MIGRADO.
    """
    manager = DatasetLifecycleManager()
    rec = manager.evaluate_catalog_precedent(
        fuente="SPVS-ASFI",
        institucion="Superintendencia de Pensiones, Valores y Seguros -> funcion valores: ASFI",
        crawler_source="asfi",
    )
    assert rec.state == DatasetLifecycleState.MIGRADO
    assert rec.transition_rule == TransitionRule.MIG_CATALOGO_HISTORICO
    assert "asfi" in rec.justification.lower()


def test_lifecycle_persistence_and_transition_audit_trail(tmp_path):
    """
    Verifica que el ciclo de vida se guarde estructurado con fecha ISO,
    estado anterior, regla de transición y resumen de conteos.
    """
    manager = DatasetLifecycleManager(output_dir=tmp_path)
    records = [
        DatasetLifecycleRecord(
            portal="asfi",
            dataset_id="balance_general",
            state=DatasetLifecycleState.VIGENTE,
            previous_state=None,
            transition_rule=TransitionRule.VIG_AL_DIA.value,
            transition_date="2026-09-24T12:00:00Z",
            last_observed_period="2026-01",
            delay_periods=0,
            recovery_attempts_exhausted=False,
            justification="Al día dentro de tolerancia.",
        ),
        DatasetLifecycleRecord(
            portal="ine",
            dataset_id="cuentas_nacionales_pib",
            state=DatasetLifecycleState.HISTORICO,
            previous_state=DatasetLifecycleState.ATRASADO.value,
            transition_rule=TransitionRule.HIST_ESCALERA_AGOTADA.value,
            transition_date="2026-09-24T12:00:00Z",
            last_observed_period="2017",
            delay_periods=9,
            recovery_attempts_exhausted=True,
            justification="Escalones 1..5 de B-54 agotados sin hallazgos.",
        ),
    ]
    target_json = tmp_path / "ciclo_vida_datasets.json"
    manager.save_lifecycle_records(records, target_json)
    assert target_json.exists()

    data = json.loads(target_json.read_text(encoding="utf-8"))
    assert "resumen_estados" in data
    assert data["resumen_estados"]["VIGENTE"] == 1
    assert data["resumen_estados"]["HISTORICO"] == 1
    assert len(data["datasets"]) == 2
