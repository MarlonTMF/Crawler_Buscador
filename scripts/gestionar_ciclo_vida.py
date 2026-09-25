"""
scripts/gestionar_ciclo_vida.py
===============================
CLI para la gestión y auditoría del ciclo de vida de datasets (B-56).

Evalúa el estado de vigencia y transición para las fuentes de BCB, INE y ASFI,
incorporando la procedencia histórica catalogada y las propuestas de herencia:
  - VIGENTE: Al día dentro de tolerancia o con huecos controlados.
  - ATRASADO: Con atraso que supera tolerancia sin agotar escalera.
  - MIGRADO: Absorbido por otra entidad (D-18 §6 o precedentes catalogados).
  - HISTORICO: Descontinuado tras agotamiento comprobado de la escalera de recuperación (B-54).

Uso:
    python scripts/gestionar_ciclo_vida.py
    python scripts/gestionar_ciclo_vida.py --sources bcb,ine,asfi
    python scripts/gestionar_ciclo_vida.py --output docs/entregas/ciclo_vida_datasets.json
"""

import argparse
from datetime import date, datetime
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple

from crawler.core.gap_detector import GapDetector, DatasetGapReport
from crawler.core.lifecycle import (
    DatasetLifecycleManager,
    DatasetLifecycleRecord,
    DatasetLifecycleState,
)
from crawler.sources.generic_adapter import GenericSourceAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Gestor de ciclo de vida de datasets (B-56)")
    parser.add_argument(
        "--sources",
        type=str,
        default="bcb,ine,asfi",
        help="Portales a evaluar separados por coma",
    )
    parser.add_argument(
        "--output-base",
        type=Path,
        default=Path("output"),
        help="Directorio base de bases de datos inventory.db",
    )
    parser.add_argument(
        "--config-base",
        type=Path,
        default=Path("config"),
        help="Directorio base de configuraciones YAML",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/entregas/ciclo_vida_datasets.json"),
        help="Ruta destino del reporte de ciclo de vida",
    )
    parser.add_argument(
        "--ref-date",
        type=str,
        default="2026-09-24",
        help="Fecha de referencia para cálculo de atrasos (YYYY-MM-DD)",
    )
    return parser.parse_args()


def load_recovery_logs() -> Dict[str, List[Dict[str, Any]]]:
    """Carga los intentos de recuperación registrados por B-54 y B-54b."""
    recovery_by_ds: Dict[str, List[Dict[str, Any]]] = {}
    for p in [Path("docs/entregas/recuperaciones_b54.json"), Path("docs/entregas/recuperaciones_b54b.json")]:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                for rec in data.get("recoveries", []):
                    ds_key = f"{rec.get('portal', '')}/{rec.get('dataset_id', '')}".lower()
                    status = rec.get("status", "")
                    success = (status == "RECOVERED")
                    attempts = recovery_by_ds.setdefault(ds_key, [])
                    period = rec.get("period")
                    rung = rec.get("recovery_rung")
                    # Evitar duplicar el mismo intento si aparece en B-54 y B-54b
                    if not any(a.get("period") == period and a.get("rung") == rung for a in attempts):
                        attempts.append({
                            "rung": rung,
                            "name": rec.get("rung_name"),
                            "period": period,
                            "success": success,
                            "url": rec.get("url"),
                            "status": status,
                        })
            except Exception as e:
                logger.warning("Error leyendo %s: %s", p, e)
    return recovery_by_ds


def load_previous_lifecycle(path: Path) -> Dict[Tuple[str, str], DatasetLifecycleRecord]:
    """Carga el estado previo de ciclo de vida si existe en disco para preservar transition_date."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Error leyendo JSON de ciclo de vida previo desde %s: %s", path, e)
        return {}

    res = {}
    for d in data.get("datasets", []):
        try:
            portal = d.get("portal", "").lower()
            ds_id = d.get("dataset_id", "").lower()
            if not portal or not ds_id:
                continue
            st_str = d.get("state")
            if not st_str:
                continue
            if st_str in DatasetLifecycleState._value2member_map_:
                state = DatasetLifecycleState(st_str)
            elif st_str in DatasetLifecycleState.__members__:
                state = DatasetLifecycleState[st_str]
            else:
                continue

            rec = DatasetLifecycleRecord(
                portal=d.get("portal", ""),
                dataset_id=d.get("dataset_id", ""),
                state=state,
                previous_state=d.get("previous_state"),
                transition_rule=d.get("transition_rule", ""),
                transition_date=d.get("transition_date", ""),
                last_observed_period=d.get("last_observed_period"),
                delay_periods=d.get("delay_periods", 0),
                recovery_attempts_exhausted=d.get("recovery_attempts_exhausted", False),
                recovery_attempts_log=d.get("recovery_attempts_log", []),
                migration_reference=d.get("migration_reference"),
                justification=d.get("justification", ""),
            )
            res[(portal, ds_id)] = rec
        except Exception as e:
            logger.warning("Saltando registro corrupto en ciclo de vida previo (%s): %s", d, e)
    return res


def load_inheritance_proposals() -> List[Dict[str, Any]]:
    """Carga propuestas de herencia institucional evaluadas en B-55."""
    path = Path("docs/entregas/propuestas_herencia.json")
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("propuestas", [])
        except Exception as e:
            logger.warning("Error leyendo propuestas de herencia: %s", e)
    return []


def load_catalog_precedents() -> List[Dict[str, Any]]:
    """Carga precedentes históricos de entidades disueltas desde el catálogo maestro."""
    cat_path = Path("output/excel_urls_diagnostic.json")
    precedents = []
    if cat_path.exists():
        try:
            data = json.loads(cat_path.read_text(encoding="utf-8"))
            for row in data:
                if row.get("crawler_no_onboard_reason") and "Procedencia historica" in row.get("crawler_no_onboard_reason", ""):
                    precedents.append(row)
        except Exception as e:
            logger.warning("Error leyendo precedentes del catálogo: %s", e)
    return precedents


def print_table(records: List[DatasetLifecycleRecord]):
    print("=" * 125)
    print("INVENTARIO Y AUDITORÍA DE CICLO DE VIDA DE DATASETS (B-56)")
    print("=" * 125)
    header = f"{'Portal':<8} {'Dataset ID':<32} {'Estado':<12} {'Regla Transición':<24} {'Último Per.':<12} {'Atraso':<8} {'Justificación'}"
    print(header)
    print("-" * 125)

    for r in records:
        st = r.state.value if isinstance(r.state, DatasetLifecycleState) else r.state
        rule = r.transition_rule.value if hasattr(r.transition_rule, "value") else str(r.transition_rule)
        last_p = r.last_observed_period or "-"
        just = (r.justification[:32] + "..") if len(r.justification) > 34 else r.justification

        print(f"{r.portal.upper():<8} {r.dataset_id:<32} {st:<12} {rule:<24} {last_p:<12} {r.delay_periods:<8} {just}")

    print("=" * 125)
    resumen = {
        "VIGENTE": sum(1 for r in records if r.state == DatasetLifecycleState.VIGENTE),
        "ATRASADO": sum(1 for r in records if r.state == DatasetLifecycleState.ATRASADO),
        "MIGRADO": sum(1 for r in records if r.state == DatasetLifecycleState.MIGRADO),
        "HISTORICO": sum(1 for r in records if r.state == DatasetLifecycleState.HISTORICO),
    }
    print(f"Resumen de estados: {resumen} (Total: {len(records)} datasets)")
    print("=" * 125)


def main():
    args = parse_args()
    ref_d = date.fromisoformat(args.ref_date)
    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]

    manager = DatasetLifecycleManager(output_dir=args.output.parent)
    previous_records = load_previous_lifecycle(args.output)
    recovery_logs = load_recovery_logs()
    proposals = load_inheritance_proposals()
    precedents = load_catalog_precedents()

    all_records: List[DatasetLifecycleRecord] = []

    # 1. Evaluar datasets de portales activos
    for src in sources:
        db_path = args.output_base / src / "inventory.db"
        cfg_path = args.config_base / f"source_{src}.yaml"

        if not db_path.exists() or not cfg_path.exists():
            continue

        adapter = GenericSourceAdapter(cfg_path)
        detector = GapDetector(db_path=db_path, reference_date=ref_d)

        for rule in adapter.dataset_rules:
            ds_id = rule.get("id")
            periodicity = rule.get("periodicity", "anual")
            tolerance = rule.get("tolerance", 1)

            gap_rep = detector.evaluate_dataset(
                dataset_id=ds_id,
                periodicity=periodicity,
                tolerance=tolerance,
            )

            ds_key = f"{src}/{ds_id}".lower()
            attempts = recovery_logs.get(ds_key, [])
            prev_rec = previous_records.get((src.lower(), ds_id.lower()))

            rec = manager.evaluate_dataset_lifecycle(
                portal=src,
                dataset_id=ds_id,
                gap_report=gap_rep,
                recovery_attempts=attempts,
                inheritance_proposals=proposals,
                previous_record=prev_rec,
            )
            all_records.append(rec)

        detector.close()

    # 2. Incorporar precedentes históricos catalogados (MIGRADO)
    for prec in precedents:
        fuente = prec.get("Fuente", "")
        inst = prec.get("Institucion", "")
        c_src = prec.get("crawler_source", "") or "catalogo"
        ds_id = fuente.lower().replace("-", "_")
        prev_rec = previous_records.get((c_src.lower(), ds_id))
        rec = manager.evaluate_catalog_precedent(
            fuente=fuente,
            institucion=inst,
            crawler_source=c_src,
            previous_record=prev_rec,
        )
        all_records.append(rec)

    # 3. Guardar y mostrar reporte
    manager.save_lifecycle_records(all_records, args.output)
    print_table(all_records)


if __name__ == "__main__":
    main()
