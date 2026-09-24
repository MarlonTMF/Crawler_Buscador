"""
Motor de detección de huecos y atrasos por dataset (B-53).
Compara períodos observados contra períodos esperados según la periodicidad
y tolerancia declarada en los archivos YAML de configuración.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class DatasetState(str, Enum):
    AL_DIA = "AL_DIA"
    ATRASADO = "ATRASADO"
    CON_HUECOS = "CON_HUECOS"
    INACTIVO = "INACTIVO"


@dataclass
class DatasetGapReport:
    dataset_id: str
    periodicity: str
    tolerance: int
    total_resources: int
    first_observed_period: Optional[str] = None
    last_observed_period: Optional[str] = None
    observed_periods_count: int = 0
    expected_periods_count: int = 0
    intermediate_gaps: List[str] = field(default_factory=list)
    delay_periods: int = 0
    state: DatasetState = DatasetState.AL_DIA
    summary: str = ""

    def to_dict(self) -> Dict:
        return {
            "dataset_id": self.dataset_id,
            "periodicity": self.periodicity,
            "tolerance": self.tolerance,
            "total_resources": self.total_resources,
            "first_observed_period": self.first_observed_period,
            "last_observed_period": self.last_observed_period,
            "observed_periods_count": self.observed_periods_count,
            "expected_periods_count": self.expected_periods_count,
            "intermediate_gaps": self.intermediate_gaps,
            "delay_periods": self.delay_periods,
            "state": self.state.value,
            "summary": self.summary,
        }


class GapDetector:
    """Detecta huecos intermedios y desfases de atraso en series documentales."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        conn: Optional[sqlite3.Connection] = None,
        reference_date: Optional[date] = None,
    ):
        if conn is not None:
            self.conn = conn
            self._owns_conn = False
        elif db_path is not None:
            self.conn = sqlite3.connect(str(db_path))
            self.conn.row_factory = sqlite3.Row
            self._owns_conn = True
        else:
            raise ValueError("Se debe proporcionar db_path o conn")

        self.reference_date = reference_date or date.today()

    def close(self):
        if self._owns_conn and self.conn:
            self.conn.close()

    @staticmethod
    def date_to_period_token(dt_str: str, periodicity: str) -> Optional[str]:
        """Convierte una fecha YYYY-MM-DD al token de período correspondiente."""
        if not dt_str or len(dt_str) < 4:
            return None
        try:
            parts = dt_str.split("-")
            y = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 1
            d = int(parts[2]) if len(parts) > 2 else 1
        except Exception:
            return None

        if periodicity == "anual":
            return f"{y:04d}"
        elif periodicity == "semestral":
            sem = 1 if m <= 6 else 2
            return f"{y:04d}-S{sem}"
        elif periodicity == "trimestral":
            tri = (m - 1) // 3 + 1
            return f"{y:04d}-Q{tri}"
        elif periodicity == "mensual":
            return f"{y:04d}-{m:02d}"
        elif periodicity == "semanal":
            dt = date(y, m, d)
            iso_year, iso_week, _ = dt.isocalendar()
            return f"{iso_year:04d}-W{iso_week:02d}"
        elif periodicity == "diaria":
            return f"{y:04d}-{m:02d}-{d:02d}"
        return dt_str

    @staticmethod
    def generate_expected_periods(start_token: str, end_token: str, periodicity: str) -> List[str]:
        """Genera la secuencia completa de tokens de períodos entre start y end inclusive."""
        if not start_token or not end_token or periodicity == "eventual":
            return []

        if start_token > end_token:
            return []

        periods = []

        if periodicity == "anual":
            y_start = int(start_token)
            y_end = int(end_token)
            for y in range(y_start, y_end + 1):
                periods.append(f"{y:04d}")

        elif periodicity == "semestral":
            y_start, s_start = int(start_token[:4]), int(start_token[-1])
            y_end, s_end = int(end_token[:4]), int(end_token[-1])
            cy, cs = y_start, s_start
            while (cy < y_end) or (cy == y_end and cs <= s_end):
                periods.append(f"{cy:04d}-S{cs}")
                cs += 1
                if cs > 2:
                    cs = 1
                    cy += 1

        elif periodicity == "trimestral":
            y_start, q_start = int(start_token[:4]), int(start_token[-1])
            y_end, q_end = int(end_token[:4]), int(end_token[-1])
            cy, cq = y_start, q_start
            while (cy < y_end) or (cy == y_end and cq <= q_end):
                periods.append(f"{cy:04d}-Q{cq}")
                cq += 1
                if cq > 4:
                    cq = 1
                    cy += 1

        elif periodicity == "mensual":
            y_start, m_start = int(start_token[:4]), int(start_token[5:7])
            y_end, m_end = int(end_token[:4]), int(end_token[5:7])
            cy, cm = y_start, m_start
            while (cy < y_end) or (cy == y_end and cm <= m_end):
                periods.append(f"{cy:04d}-{cm:02d}")
                cm += 1
                if cm > 12:
                    cm = 1
                    cy += 1

        elif periodicity == "semanal":
            y_start, w_start = int(start_token[:4]), int(start_token[6:8])
            y_end, w_end = int(end_token[:4]), int(end_token[6:8])
            from datetime import timedelta
            dt_curr = date.fromisocalendar(y_start, w_start, 1)
            dt_end = date.fromisocalendar(y_end, w_end, 1)
            while dt_curr <= dt_end:
                y, w, _ = dt_curr.isocalendar()
                periods.append(f"{y:04d}-W{w:02d}")
                dt_curr += timedelta(weeks=1)

        elif periodicity == "diaria":
            dt_curr = date.fromisoformat(start_token)
            dt_end = date.fromisoformat(end_token)
            from datetime import timedelta
            while dt_curr <= dt_end:
                periods.append(dt_curr.isoformat())
                dt_curr += timedelta(days=1)
        else:
            raise ValueError(f"Periodicidad no soportada: {periodicity}")

        return periods

    def evaluate_dataset(
        self,
        dataset_id: str,
        periodicity: str = "anual",
        tolerance: int = 1,
    ) -> DatasetGapReport:
        """Evalúa un dataset contra la base de inventario y genera el reporte de huecos y atrasos."""
        cursor = self.conn.execute(
            "SELECT canonical_url, period_start, period_end, published_at FROM resource_audit_log WHERE dataset_id = ?",
            (dataset_id,)
        )
        rows = cursor.fetchall()
        total_rows = len(rows)

        if periodicity == "eventual":
            return DatasetGapReport(
                dataset_id=dataset_id,
                periodicity=periodicity,
                tolerance=tolerance,
                total_resources=total_rows,
                state=DatasetState.AL_DIA,
                summary="Dataset aperiódico / eventual (sin calendario periódico requerido)",
            )

        if total_rows == 0:
            return DatasetGapReport(
                dataset_id=dataset_id,
                periodicity=periodicity,
                tolerance=tolerance,
                total_resources=0,
                state=DatasetState.INACTIVO,
                summary="Dataset sin registros en la base de inventario",
            )

        # Mapear registros a tokens de período
        observed_tokens: Set[str] = set()
        for r in rows:
            # Soportar tanto sqlite3.Row como tupla común
            p_start = r[1] if isinstance(r, (tuple, list)) else r["period_start"]
            p_end = r[2] if isinstance(r, (tuple, list)) else r["period_end"]
            pub_at = r[3] if isinstance(r, (tuple, list)) else r["published_at"]

            # Preferir period_start, fallback a published_at
            dt = p_start or pub_at
            if dt:
                tok = self.date_to_period_token(dt, periodicity)
                if tok:
                    observed_tokens.add(tok)

        if not observed_tokens:
            return DatasetGapReport(
                dataset_id=dataset_id,
                periodicity=periodicity,
                tolerance=tolerance,
                total_resources=total_rows,
                state=DatasetState.INACTIVO,
                summary="Dataset con registros pero sin fechas identificables",
            )

        sorted_tokens = sorted(observed_tokens)
        first_tok = sorted_tokens[0]
        last_tok = sorted_tokens[-1]

        # Período de referencia (hoy)
        ref_tok = self.date_to_period_token(self.reference_date.isoformat(), periodicity)

        # 1. Huecos intermedios: esperados entre first_tok y last_tok
        expected_between = self.generate_expected_periods(first_tok, last_tok, periodicity)
        intermediate_gaps = [p for p in expected_between if p not in observed_tokens]

        # 2. Atraso: períodos esperados entre last_tok y ref_tok
        periods_to_ref = self.generate_expected_periods(last_tok, ref_tok, periodicity)
        # El atraso cuenta cuántos períodos posteriores a last_tok no existen
        pending_to_ref = [p for p in periods_to_ref if p != last_tok and p not in observed_tokens]
        delay_count = len(pending_to_ref)

        # 3. Determinación de inactividad vs atraso
        # Si no hay publicaciones en más de 2 años (o períodos completos más allá de la tolerancia)
        is_inactive = False
        if periodicity == "anual" and delay_count >= (tolerance + 2):
            is_inactive = True
        elif periodicity == "semestral" and delay_count >= (tolerance + 4):
            is_inactive = True
        elif periodicity == "trimestral" and delay_count >= (tolerance + 6):
            is_inactive = True
        elif periodicity == "mensual" and delay_count >= (tolerance + 18):
            is_inactive = True
        elif periodicity == "semanal" and delay_count >= (tolerance + 8):
            is_inactive = True
        elif periodicity == "diaria" and delay_count >= (tolerance + 30):
            is_inactive = True

        # Estado resultante
        if is_inactive:
            state = DatasetState.INACTIVO
            summary = f"Inactivo: sin publicaciones desde {last_tok} ({delay_count} períodos de atraso acumulados)"
        elif len(intermediate_gaps) > 0:
            state = DatasetState.CON_HUECOS
            summary = f"Con huecos: {len(intermediate_gaps)} períodos faltantes entre {first_tok} y {last_tok}"
            if delay_count > tolerance:
                summary += f" (y atraso de {delay_count} períodos)"
        elif delay_count > tolerance:
            state = DatasetState.ATRASADO
            summary = f"Atrasado: {delay_count} períodos desde {last_tok} (tolerancia: {tolerance})"
        else:
            state = DatasetState.AL_DIA
            summary = f"Al día: último período {last_tok} dentro de la tolerancia ({delay_count} <= {tolerance})"

        return DatasetGapReport(
            dataset_id=dataset_id,
            periodicity=periodicity,
            tolerance=tolerance,
            total_resources=total_rows,
            first_observed_period=first_tok,
            last_observed_period=last_tok,
            observed_periods_count=len(observed_tokens),
            expected_periods_count=len(expected_between),
            intermediate_gaps=intermediate_gaps,
            delay_periods=delay_count,
            state=state,
            summary=summary,
        )
