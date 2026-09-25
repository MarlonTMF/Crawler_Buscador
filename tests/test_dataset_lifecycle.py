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


def test_lifecycle_load_recovery_logs_real_json():
    """
    H-1: Verifica que load_recovery_logs cargue la clave 'recoveries' de los
    JSON reales de B-54 y que 'bcb/deuda_externa' contenga intentos exitosos.
    """
    from scripts.gestionar_ciclo_vida import load_recovery_logs

    logs_by_ds = load_recovery_logs()
    assert "bcb/deuda_externa" in logs_by_ds, "bcb/deuda_externa debe tener intentos de recuperación en B-54"

    deuda_logs = logs_by_ds["bcb/deuda_externa"]
    assert len(deuda_logs) >= 3, f"Esperaba al menos 3 intentos, obtuve {len(deuda_logs)}"
    for log in deuda_logs:
        assert log["rung"] == 2
        assert log["status"] == "RECOVERED"
        assert log["success"] is True
        assert log["url"]


def test_lifecycle_transition_date_stable_across_runs():
    """
    H-2: Verifica que cuando el estado de un dataset no cambia entre corridas,
    su transition_date se mantenga inalterada y previous_state se registre.
    Cuando el estado cambia, transition_date debe actualizarse con la nueva fecha.
    """
    manager = DatasetLifecycleManager()
    gap_rep1 = DatasetGapReport(
        dataset_id="boletin_mensual",
        periodicity="mensual",
        tolerance=2,
        total_resources=12,
        first_observed_period="2025-01",
        last_observed_period="2026-08",
        delay_periods=1,
        state=DatasetState.AL_DIA,
    )

    # 1era corrida: nuevo dataset
    rec1 = manager.evaluate_dataset_lifecycle(
        portal="asfi",
        dataset_id="boletin_mensual",
        gap_report=gap_rep1,
        previous_record=None,
    )
    assert rec1.state == DatasetLifecycleState.VIGENTE
    assert rec1.previous_state is None
    date_run1 = rec1.transition_date

    # 2da corrida: mismo estado VIGENTE -> transition_date debe ser IDÉNTICA
    rec2 = manager.evaluate_dataset_lifecycle(
        portal="asfi",
        dataset_id="boletin_mensual",
        gap_report=gap_rep1,
        previous_record=rec1,
    )
    assert rec2.state == DatasetLifecycleState.VIGENTE
    assert rec2.transition_date == date_run1
    assert rec2.previous_state == DatasetLifecycleState.VIGENTE.value

    # 3ra corrida: cambia a ATRASADO -> transition_date debe ser NUEVA
    gap_rep_atrasado = DatasetGapReport(
        dataset_id="boletin_mensual",
        periodicity="mensual",
        tolerance=2,
        total_resources=12,
        first_observed_period="2025-01",
        last_observed_period="2026-01",
        delay_periods=8,
        state=DatasetState.ATRASADO,
    )
    rec3 = manager.evaluate_dataset_lifecycle(
        portal="asfi",
        dataset_id="boletin_mensual",
        gap_report=gap_rep_atrasado,
        previous_record=rec2,
    )
    assert rec3.state == DatasetLifecycleState.ATRASADO
    assert rec3.previous_state == DatasetLifecycleState.VIGENTE.value
    assert rec3.transition_rule == TransitionRule.ATR_BUSQUEDA_PENDIENTE.value


def test_lifecycle_d18_exact_matching():
    """
    O-2: Cotejo exacto de (portal, dataset_id). Subcadenas no deben provocar
    migraciones accidentales bajo D-18.
    """
    manager = DatasetLifecycleManager()
    gap_rep = DatasetGapReport(
        dataset_id="cuentas_nacionales_pib",
        periodicity="anual",
        tolerance=1,
        total_resources=10,
        first_observed_period="2000",
        last_observed_period="2020",
        delay_periods=5,
        state=DatasetState.ATRASADO,
    )
    # Propuesta para un dataset distinto pero que contiene la subcadena
    proposal_distinct = {
        "origen_portal": "ine",
        "origen_dataset": "cuentas_nacionales_pib_trimestral",
        "destino_entidad": "BCB",
        "status": "ACEPTADA",
    }
    rec = manager.evaluate_dataset_lifecycle(
        portal="ine",
        dataset_id="cuentas_nacionales_pib",
        gap_report=gap_rep,
        inheritance_proposals=[proposal_distinct],
    )
    # No debe migrar porque no es coincidencia exacta
    assert rec.state != DatasetLifecycleState.MIGRADO
    assert rec.state == DatasetLifecycleState.ATRASADO


def test_lifecycle_vigente_sin_periodicidad():
    """
    O-3: Un dataset sin periodicidad o sin períodos temporales medibles
    recibe la regla VIG_SIN_PERIODICIDAD en lugar de VIG_AL_DIA.
    """
    manager = DatasetLifecycleManager()
    gap_rep = DatasetGapReport(
        dataset_id="memorias_institucionales",
        periodicity="anual",
        tolerance=0,
        total_resources=15,
        first_observed_period=None,
        last_observed_period=None,
        delay_periods=0,
        state=DatasetState.AL_DIA,
    )
    rec = manager.evaluate_dataset_lifecycle(
        portal="bcb",
        dataset_id="memorias_institucionales",
        gap_report=gap_rep,
    )
    assert rec.state == DatasetLifecycleState.VIGENTE
    assert rec.transition_rule == TransitionRule.VIG_SIN_PERIODICIDAD.value
    assert "sin periodicidad declarada" in rec.justification.lower()


def test_lifecycle_transition_date_updates_when_rule_changes_same_state():
    """
    O-2: Verifica que cuando un dataset cambia su regla de transición
    (ej. VIG_AL_DIA -> VIG_SIN_PERIODICIDAD) aun manteniendo el estado VIGENTE,
    la fecha transition_date se actualice adecuadamente.
    """
    manager = DatasetLifecycleManager()
    gap_rep1 = DatasetGapReport(
        dataset_id="boletin_mensual",
        periodicity="mensual",
        tolerance=2,
        total_resources=12,
        first_observed_period="2025-01",
        last_observed_period="2026-08",
        delay_periods=1,
        state=DatasetState.AL_DIA,
    )
    rec1 = manager.evaluate_dataset_lifecycle(
        portal="asfi",
        dataset_id="boletin_mensual",
        gap_report=gap_rep1,
        previous_record=None,
    )
    rec1.transition_date = "2026-09-20T10:00:00Z"
    assert rec1.transition_rule == TransitionRule.VIG_AL_DIA.value

    # Cambia a sin periodicidad (mismo estado VIGENTE, distinta regla)
    gap_rep2 = DatasetGapReport(
        dataset_id="boletin_mensual",
        periodicity="mensual",
        tolerance=2,
        total_resources=12,
        first_observed_period=None,
        last_observed_period=None,
        delay_periods=0,
        state=DatasetState.AL_DIA,
    )
    rec2 = manager.evaluate_dataset_lifecycle(
        portal="asfi",
        dataset_id="boletin_mensual",
        gap_report=gap_rep2,
        previous_record=rec1,
    )
    assert rec2.state == DatasetLifecycleState.VIGENTE
    assert rec2.transition_rule == TransitionRule.VIG_SIN_PERIODICIDAD.value
    # La fecha debe haber cambiado porque la regla cambió
    assert rec2.transition_date != rec1.transition_date


def test_lifecycle_load_previous_disk_roundtrip_and_graceful_degradation(tmp_path):
    """
    O-4 y O-5: Verifica el ciclo completo de persistencia e ida y vuelta por disco
    de load_previous_lifecycle, y asegura que una fila corrupta (state: null)
    no descarte las filas sanas del reporte.
    """
    from scripts.gestionar_ciclo_vida import load_previous_lifecycle

    test_file = tmp_path / "ciclo_vida_corrupto.json"
    content = {
        "timestamp": "2026-09-25T00:00:00Z",
        "datasets": [
            {
                "portal": "bcb",
                "dataset_id": "boletines_mensuales",
                "state": "VIGENTE",
                "transition_rule": "VIG_AL_DIA",
                "transition_date": "2026-09-20T10:00:00Z",
                "delay_periods": 0,
                "recovery_attempts_log": [],
                "justification": "Al día",
            },
            {
                "portal": "ine",
                "dataset_id": "fila_corrupta",
                "state": None,  # Fila corrupta que debe ser saltada
                "transition_rule": "CORRUPTA",
                "transition_date": "2026-09-20T10:00:00Z",
            }
        ]
    }
    test_file.write_text(json.dumps(content), encoding="utf-8")

    loaded = load_previous_lifecycle(test_file)
    # Debe recuperar la fila sana sin perderla por culpa de la corrupta
    assert len(loaded) == 1, f"Esperaba 1 registro recuperado, obtuve {len(loaded)}"
    rec = loaded.get(("bcb", "boletines_mensuales"))
    assert rec is not None
    assert rec.state == DatasetLifecycleState.VIGENTE
    assert rec.transition_date == "2026-09-20T10:00:00Z"
