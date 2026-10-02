"""Catálogo de producción de SPIM, leído en modo de solo lectura.

SPIM es el sistema de producción de DATAX. Su respaldo PostgreSQL
(``backup_10.0.0.12``, gitignorado y sensible) contiene, en las tablas
``source`` y ``file``, la definición oficial de cada serie que DATAX mantiene:
su periodicidad, su URL y hasta qué fecha está actualizada. Es la misma fuente
que usa el cargador del prospector interno; aquí se lee directamente, sin
importar su código.

Solo se leen esas dos tablas. El respaldo contiene otras con información
sensible que este módulo no toca.

Dos particularidades del dato, verificadas el 2026-10-02:

* La fuente con ``id_source = 1`` (BCB) funciona como cajón por defecto: tiene
  516 de las 586 series, incluidas algunas de salud o deportes. La institución
  real se obtiene del dominio de la URL, no de ``id_source``.
* La frecuencia es texto libre: «Mensual», «mensual», «Semestral», «-».
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

# Dominio (o sufijo de dominio) -> portal de este proyecto.
INSTITUTION_BY_DOMAIN = {
    "bcb.gob.bo": "bcb",
    "ine.gob.bo": "ine",
    "asfi.gob.bo": "asfi",
}

# Desfase de publicación tolerado, en meses, antes de considerar atrasada una
# serie. Un dato mensual de junio suele publicarse en julio o agosto; un dato
# anual de 2025, durante 2026.
TOLERANCIA_MESES = {
    "diaria": 0.5,
    "semanal": 1,
    "mensual": 3,
    "trimestral": 6,
    "semestral": 9,
    "anual": 18,
}

_EMPTY = {"", "-", "vacio", "no-data", "null", "none"}


@dataclass(frozen=True)
class SpimSeries:
    code: str
    name: str
    institution: Optional[str]
    source_short_name: str
    periodicity: Optional[str]
    url: str
    last_file_url: Optional[str]
    updated_to: Optional[date]
    last_update: Optional[date]
    state: Optional[str]


@dataclass(frozen=True)
class CurrencyEvaluation:
    series: SpimSeries
    status: str
    months_behind: Optional[float]
    tolerance_months: Optional[float]


def _clean(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in _EMPTY else text


def normalize_periodicity(raw) -> Optional[str]:
    """Normaliza la frecuencia de texto libre de SPIM.

    A diferencia del cargador del prospector interno, reconoce «semestral»
    (allá cae en ON_DEMAND) y devuelve ``None`` cuando el dato no existe.
    """
    text = _clean(raw)
    if text is None:
        return None
    t = text.lower()
    for clave, valor in (
        ("diari", "diaria"),
        ("seman", "semanal"),
        ("mensua", "mensual"),
        ("bimestr", "bimestral"),
        ("trimestr", "trimestral"),
        ("semestr", "semestral"),
        ("anual", "anual"),
    ):
        if clave in t:
            return valor
    return None


def institution_for_url(url: Optional[str]) -> Optional[str]:
    host = urlparse((url or "").strip()).netloc.lower().split(":")[0]
    for dominio, portal in INSTITUTION_BY_DOMAIN.items():
        if host == dominio or host.endswith("." + dominio):
            return portal
    return None


def _to_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def rows_to_series(source_rows: Iterable[dict], file_rows: Iterable[dict]) -> list[SpimSeries]:
    """Convierte filas de ``source`` y ``file`` (como dicts) en series normalizadas."""
    sources = {r.get("id_source"): r for r in source_rows}
    series: list[SpimSeries] = []
    for f in file_rows:
        url = _clean(f.get("specific_url")) or _clean(f.get("main_url")) or ""
        src = sources.get(f.get("id_source"), {})
        series.append(SpimSeries(
            code=_clean(f.get("code")) or f"FILE_{f.get('id_file')}",
            name=_clean(f.get("name")) or "",
            institution=institution_for_url(url),
            source_short_name=_clean(src.get("short_name")) or "",
            periodicity=normalize_periodicity(f.get("publication_frequency")),
            url=url,
            last_file_url=_clean(f.get("last_file_url")),
            updated_to=_to_date(f.get("updated_to")),
            last_update=_to_date(f.get("update_date")),
            state=_clean(f.get("state")),
        ))
    return series


def _table_rows(dump, table: str) -> list[dict]:
    entry = next(e for e in dump.entries if e.desc == "TABLE DATA" and e.tag == table)
    m = re.search(r"COPY\s+\S+\s*\(([^)]*)\)", entry.copy_stmt or "")
    if not m:
        raise ValueError(f"No se pudo leer el orden de columnas de '{table}'")
    cols = [c.strip().strip('"') for c in m.group(1).split(",")]
    return [dict(zip(cols, row)) for row in dump.table_data(entry.namespace, table)]


def load_spim_series(backup_path: Path) -> list[SpimSeries]:
    """Lee las series del respaldo de SPIM. Requiere el extra ``spim`` (pgdumplib)."""
    import pgdumplib  # dependencia opcional

    dump = pgdumplib.load(str(backup_path))
    return rows_to_series(_table_rows(dump, "source"), _table_rows(dump, "file"))


def snapshot_date(series: Iterable[SpimSeries]) -> Optional[date]:
    """Fecha de la foto del respaldo: la última modificación registrada."""
    fechas = [s.last_update for s in series if s.last_update]
    return max(fechas) if fechas else None


def _months_between(earlier: date, later: date) -> float:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month) + (later.day - earlier.day) / 30.0


def evaluate_currency(s: SpimSeries, ref_date: date) -> CurrencyEvaluation:
    """Clasifica la vigencia de una serie respecto de una fecha de referencia.

    Estados: AL_DIA, ATRASADA, FECHA_FUTURA (dato inconsistente: actualizada a
    una fecha posterior a la referencia), SIN_PERIODICIDAD y SIN_FECHA.
    """
    if s.periodicity is None or s.periodicity not in TOLERANCIA_MESES:
        return CurrencyEvaluation(s, "SIN_PERIODICIDAD", None, None)
    if s.updated_to is None:
        return CurrencyEvaluation(s, "SIN_FECHA", None, TOLERANCIA_MESES[s.periodicity])
    tol = TOLERANCIA_MESES[s.periodicity]
    months = _months_between(s.updated_to, ref_date)
    if months < -1:
        return CurrencyEvaluation(s, "FECHA_FUTURA", round(months, 1), tol)
    status = "ATRASADA" if months > tol else "AL_DIA"
    return CurrencyEvaluation(s, status, round(months, 1), tol)
