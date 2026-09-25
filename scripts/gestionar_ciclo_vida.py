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
from typing import Any, Dict, List

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
                for rec in data.get("recovered_periods", []):
                    ds_key = f"{rec.get('portal', '')}/{rec.get('dataset_id', '')}".lower()
                    recovery_by_ds.setdefault(ds_key, []).append({
                        "rung": rec.get("recovery_rung"),
                        "name": rec.get("rung_name"),
                        "period": rec.get("period"),
                        "success": True,
                        "url": rec.get("url"),
                    })
            except Exception as e:
                logger.warning("Error leyendo %s: %s", p, e)
    return recovery_by_ds


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

            rec = manager.evaluate_dataset_lifecycle(
                portal=src,
                dataset_id=ds_id,
                gap_report=gap_rep,
                recovery_attempts=attempts,
                inheritance_proposals=proposals,
            )
            all_records.append(rec)

        detector.close()

    # 2. Incorporar precedentes históricos catalogados (MIGRADO)
    for prec in precedents:
        fuente = prec.get("Fuente", "")
        inst = prec.get("Institucion", "")
        c_src = prec.get("crawler_source", "") or "catalogo"
        rec = manager.evaluate_catalog_precedent(
            fuente=fuente,
            institucion=inst,
            crawler_source=c_src,
        )
        all_records.append(rec)

    # 3. Guardar y mostrar reporte
    manager.save_lifecycle_records(all_records, args.output)
    print_table(all_records)


if __name__ == "__main__":
    main()
