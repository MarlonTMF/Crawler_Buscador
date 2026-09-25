"""
crawler/core/lifecycle.py
=========================
Gestor del ciclo de vida de series documentales y datasets (B-56).

Implementa los estados explícitos de ciclo de vida por dataset:
  - VIGENTE: Al día dentro de tolerancia o con huecos intermedios controlados.
  - ATRASADO: Con atraso que excede la tolerancia pero cuya búsqueda no se ha agotado.
  - MIGRADO: Serie absorbida por otra entidad pública sucesora bajo D-18 §6
             (requiere herencia ACEPTADA o precedencia histórica catalogada).
  - HISTORICO: Serie extinta o descontinuada tras AGOTAR de forma comprobada
               todos los escalones de la escalera de recuperación (B-54/B-54b).

Regla inviolable (B-56):
  El paso a HISTORICO nunca es automático por silencio: exige que la escalera de B-54
  se haya agotado y quede registrado qué se intentó con detalle auditable.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from crawler.core.gap_detector import DatasetGapReport, DatasetState

logger = logging.getLogger(__name__)


class DatasetLifecycleState(str, Enum):
    VIGENTE = "VIGENTE"
    ATRASADO = "ATRASADO"
    MIGRADO = "MIGRADO"
    HISTORICO = "HISTORICO"


class TransitionRule(str, Enum):
    VIG_AL_DIA = "VIG_AL_DIA"
    VIG_SIN_PERIODICIDAD = "VIG_SIN_PERIODICIDAD"
    ATR_BUSQUEDA_PENDIENTE = "ATR_BUSQUEDA_PENDIENTE"
    HIST_ESCALERA_AGOTADA = "HIST_ESCALERA_AGOTADA"
    MIG_D18_ACEPTADA = "MIG_D18_ACEPTADA"
    MIG_CATALOGO_HISTORICO = "MIG_CATALOGO_HISTORICO"


@dataclass
class DatasetLifecycleRecord:
    portal: str
    dataset_id: str
    state: DatasetLifecycleState
    transition_rule: str
    transition_date: str
    previous_state: Optional[str] = None
    last_observed_period: Optional[str] = None
    delay_periods: int = 0
    recovery_attempts_exhausted: bool = False
    recovery_attempts_log: List[Dict[str, Any]] = field(default_factory=list)
    migration_reference: Optional[Dict[str, Any]] = None
    justification: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portal": self.portal,
            "dataset_id": self.dataset_id,
            "state": self.state.value if isinstance(self.state, DatasetLifecycleState) else self.state,
            "previous_state": self.previous_state,
            "transition_rule": self.transition_rule.value if isinstance(self.transition_rule, TransitionRule) else self.transition_rule,
            "transition_date": self.transition_date,
            "last_observed_period": self.last_observed_period,
            "delay_periods": self.delay_periods,
            "recovery_attempts_exhausted": self.recovery_attempts_exhausted,
            "recovery_attempts_log": self.recovery_attempts_log,
            "migration_reference": self.migration_reference,
            "justification": self.justification,
        }


class DatasetLifecycleManager:
    """Gestor de ciclo de vida con reglas auditables de transición y archivado justificado."""

    # Escalones requeridos para considerar formalmente agotada la escalera determinista
    MANDATORY_RUNGS_FOR_EXHAUSTION = {1, 2, 3, 4}

    def __init__(self, output_dir: Path = Path("docs/entregas")):
        self.output_dir = output_dir

    def evaluate_dataset_lifecycle(
        self,
        portal: str,
        dataset_id: str,
        gap_report: DatasetGapReport,
        recovery_attempts: Optional[List[Dict[str, Any]]] = None,
        inheritance_proposals: Optional[List[Dict[str, Any]]] = None,
        previous_record: Optional[DatasetLifecycleRecord] = None,
        previous_state: Optional[str] = None,
    ) -> DatasetLifecycleRecord:
        """
        Evalúa y asigna el estado de ciclo de vida para un dataset según evidencia objetiva.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        attempts = recovery_attempts or []
        proposals = inheritance_proposals or []

        # Determinar estado previo
        if previous_record is not None:
            prev_st = previous_record.state.value if isinstance(previous_record.state, DatasetLifecycleState) else previous_record.state
        else:
            prev_st = previous_state

        def _resolve_transition_date(target_st: DatasetLifecycleState) -> str:
            if previous_record is not None and previous_record.state == target_st and previous_record.transition_date:
                return previous_record.transition_date
            return now_iso

        # -------------------------------------------------------------
        # 1. Regla de Migración (D-18 §6)
        # Una herencia ACEPTADA es lo único que lleva un dataset a MIGRADO.
        # Cotejo por igualdad exacta de (portal, dataset_id).
        # -------------------------------------------------------------
        for prop in proposals:
            orig_p = prop.get("origen_portal", "").strip().lower()
            orig_ds = prop.get("origen_dataset", "").strip().lower()
            status = prop.get("status", "")

            matches_ds = (orig_p == portal.strip().lower() and orig_ds == dataset_id.strip().lower())
            if matches_ds and status == "ACEPTADA":
                tgt_st = DatasetLifecycleState.MIGRADO
                return DatasetLifecycleRecord(
                    portal=portal,
                    dataset_id=dataset_id,
                    state=tgt_st,
                    previous_state=prev_st,
                    transition_rule=TransitionRule.MIG_D18_ACEPTADA.value,
                    transition_date=_resolve_transition_date(tgt_st),
                    last_observed_period=gap_report.last_observed_period,
                    delay_periods=gap_report.delay_periods,
                    recovery_attempts_exhausted=False,
                    recovery_attempts_log=[],
                    migration_reference=prop,
                    justification=f"Serie migrada formalmente a '{prop.get('destino_entidad')}' mediante herencia ACEPTADA bajo D-18 §6.",
                )

        # -------------------------------------------------------------
        # 2. Regla de Vigencia: al día dentro de tolerancia
        # -------------------------------------------------------------
        if gap_report.delay_periods == 0 and gap_report.last_observed_period is None:
            tgt_st = DatasetLifecycleState.VIGENTE
            return DatasetLifecycleRecord(
                portal=portal,
                dataset_id=dataset_id,
                state=tgt_st,
                previous_state=prev_st,
                transition_rule=TransitionRule.VIG_SIN_PERIODICIDAD.value,
                transition_date=_resolve_transition_date(tgt_st),
                last_observed_period=None,
                delay_periods=0,
                recovery_attempts_exhausted=False,
                recovery_attempts_log=attempts,
                migration_reference=None,
                justification="Serie vigente sin periodicidad declarada o sin períodos temporales evaluados.",
            )

        if gap_report.delay_periods <= gap_report.tolerance:
            tgt_st = DatasetLifecycleState.VIGENTE
            return DatasetLifecycleRecord(
                portal=portal,
                dataset_id=dataset_id,
                state=tgt_st,
                previous_state=prev_st,
                transition_rule=TransitionRule.VIG_AL_DIA.value,
                transition_date=_resolve_transition_date(tgt_st),
                last_observed_period=gap_report.last_observed_period,
                delay_periods=gap_report.delay_periods,
                recovery_attempts_exhausted=False,
                recovery_attempts_log=attempts,
                migration_reference=None,
                justification=f"Serie vigente: retraso de {gap_report.delay_periods} período(s) dentro de la tolerancia permitida ({gap_report.tolerance}).",
            )

        # -------------------------------------------------------------
        # 3. Regla de Atraso vs Histórico (B-56 Criterio de Aceptación)
        # El paso a HISTORICO exige que la escalera de B-54 se haya agotado.
        # Nunca es automático por silencio prolongado.
        # -------------------------------------------------------------
        rungs_tested = {att.get("rung") for att in attempts if att.get("rung") is not None}
        all_failed = all(not att.get("success", False) for att in attempts) if attempts else False

        # Comprobar si se agotaron los escalones deterministas obligatorios (1..4)
        ladder_exhausted = (
            bool(attempts)
            and all_failed
            and self.MANDATORY_RUNGS_FOR_EXHAUSTION.issubset(rungs_tested)
        )

        if ladder_exhausted:
            tgt_st = DatasetLifecycleState.HISTORICO
            return DatasetLifecycleRecord(
                portal=portal,
                dataset_id=dataset_id,
                state=tgt_st,
                previous_state=prev_st,
                transition_rule=TransitionRule.HIST_ESCALERA_AGOTADA.value,
                transition_date=_resolve_transition_date(tgt_st),
                last_observed_period=gap_report.last_observed_period,
                delay_periods=gap_report.delay_periods,
                recovery_attempts_exhausted=True,
                recovery_attempts_log=attempts,
                migration_reference=None,
                justification=f"Archivado justificado a histórico: se agotaron los escalones {sorted(list(rungs_tested))} de la escalera de recuperación B-54 sin hallar el período faltante.",
            )

        # Si el retraso excede la tolerancia pero la escalera no se agotó: ATRASADO
        tgt_st = DatasetLifecycleState.ATRASADO
        missing_rungs = sorted(list(self.MANDATORY_RUNGS_FOR_EXHAUSTION - rungs_tested))
        return DatasetLifecycleRecord(
            portal=portal,
            dataset_id=dataset_id,
            state=tgt_st,
            previous_state=prev_st,
            transition_rule=TransitionRule.ATR_BUSQUEDA_PENDIENTE.value,
            transition_date=_resolve_transition_date(tgt_st),
            last_observed_period=gap_report.last_observed_period,
            delay_periods=gap_report.delay_periods,
            recovery_attempts_exhausted=False,
            recovery_attempts_log=attempts,
            migration_reference=None,
            justification=f"Dataset con retraso ({gap_report.delay_periods} períodos > tolerancia {gap_report.tolerance}) pero la búsqueda no ha concluido: no se han agotado todos los escalones de la escalera B-54 (pendientes: {missing_rungs or 'todos'}).",
        )

    def evaluate_catalog_precedent(
        self,
        fuente: str,
        institucion: str,
        crawler_source: str,
        previous_record: Optional[DatasetLifecycleRecord] = None,
        previous_state: Optional[str] = None,
    ) -> DatasetLifecycleRecord:
        """
        Evalúa precedentes históricos catalogados (entidades disueltas como SPVS, SUPTRANS).
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        if previous_record is not None:
            prev_st = previous_record.state.value if isinstance(previous_record.state, DatasetLifecycleState) else previous_record.state
            t_date = previous_record.transition_date if (previous_record.state == DatasetLifecycleState.MIGRADO and previous_record.transition_date) else now_iso
        else:
            prev_st = previous_state
            t_date = now_iso

        return DatasetLifecycleRecord(
            portal=crawler_source,
            dataset_id=fuente.lower().replace("-", "_"),
            state=DatasetLifecycleState.MIGRADO,
            previous_state=prev_st,
            transition_rule=TransitionRule.MIG_CATALOGO_HISTORICO.value,
            transition_date=t_date,
            last_observed_period=None,
            delay_periods=0,
            recovery_attempts_exhausted=False,
            recovery_attempts_log=[],
            migration_reference={
                "fuente": fuente,
                "institucion": institucion,
                "crawler_source": crawler_source,
            },
            justification=f"Precedente histórico catalogado: entidad absorbida por '{crawler_source.upper()}' ({institucion}).",
        )

    def save_lifecycle_records(
        self,
        records: List[DatasetLifecycleRecord],
        output_file: Optional[Path] = None,
    ):
        """Guarda el inventario completo de ciclo de vida con agregados de auditoría."""
        target = output_file or (self.output_dir / "ciclo_vida_datasets.json")
        target.parent.mkdir(parents=True, exist_ok=True)

        out = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "criterio": "B-56 (Ciclo de vida de datasets y archivado justificado)",
            "total_datasets": len(records),
            "resumen_estados": {
                "VIGENTE": sum(1 for r in records if r.state == DatasetLifecycleState.VIGENTE),
                "ATRASADO": sum(1 for r in records if r.state == DatasetLifecycleState.ATRASADO),
                "MIGRADO": sum(1 for r in records if r.state == DatasetLifecycleState.MIGRADO),
                "HISTORICO": sum(1 for r in records if r.state == DatasetLifecycleState.HISTORICO),
            },
            "datasets": [r.to_dict() for r in records],
        }
        target.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Registro de ciclo de vida guardado en %s", target)
