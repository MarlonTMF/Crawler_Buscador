"""
scripts/evaluar_herencia.py
===========================
CLI para la evaluación de propuestas de herencia institucional (B-55 / Decisión D-18).

Evalúa candidatos de herencia institucional (provenientes de cola_herencia_b55.json
o del catálogo maestro) aplicando estrictamente las cuatro compuertas copulativas
de evidencia descargada:
  1. Continuidad temporal (falsador C-2).
  2. Respaldo legal con procedencia obligatoria de bytes C-1 (mención del predecesor o norma).
  3. Identidad estructural sobre documentos D-14 / C-4 (.pdf, .xlsx, etc. nunca HTML).
  4. Identidad institucional del destino bajo D-01 / C-3 (con descarte de domain parking).

Uso:
    python scripts/evaluar_herencia.py
    python scripts/evaluar_herencia.py --input docs/entregas/cola_herencia_b55.json --output docs/entregas/propuestas_herencia.json
"""

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import List

from crawler.core.inheritance_evaluator import (
    InheritanceCandidate,
    InheritanceEvaluator,
    InheritanceProposal,
    ProposalStatus,
    GateResult,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluador de herencia institucional (B-55 / D-18)")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("docs/entregas/cola_herencia_b55.json"),
        help="Archivo JSON con candidatos crudos de herencia",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/entregas/propuestas_herencia.json"),
        help="Ruta donde guardar las propuestas evaluadas",
    )
    return parser.parse_args()


def load_candidates(input_path: Path, evaluator: InheritanceEvaluator) -> List[InheritanceCandidate]:
    candidates = []
    if input_path.exists():
        try:
            raw = json.loads(input_path.read_text(encoding="utf-8"))
            items = raw if isinstance(raw, list) else raw.get("candidates", [])
            for it in items:
                candidates.append(
                    InheritanceCandidate(
                        origen_entidad=it.get("origen_entidad", "Desconocido"),
                        origen_portal=it.get("origen_portal", "desconocido"),
                        origen_dataset=it.get("origen_dataset", "desconocido"),
                        destino_entidad=it.get("destino_entidad", "Desconocido"),
                        destino_url=it.get("destino_url", ""),
                        ultimo_periodo_origen=it.get("ultimo_periodo_origen"),
                        primer_periodo_destino=it.get("primer_periodo_destino"),
                        origen_agente=it.get("origen_agente", False),
                        modelo_cita_legal_sugerida=it.get("modelo_cita_legal_sugerida"),
                    )
                )
            logger.info("Cargados %d candidatos desde %s", len(candidates), input_path)
        except Exception as e:
            logger.warning("Error leyendo %s: %s", input_path, e)

    if not candidates:
        logger.info("Cola no encontrada o vacía. Cargando candidatos desde catálogo maestro...")
        candidates = evaluator.load_candidates_from_catalog()
        logger.info("Cargados %d candidatos del catálogo", len(candidates))

    return candidates


def print_report(proposals: List[InheritanceProposal]):
    print("=" * 120)
    print("REPORTE DE EVALUACIÓN DE PROPUESTAS DE HERENCIA INSTITUCIONAL (B-55 / D-18)")
    print("=" * 120)
    if not proposals:
        print("No se evaluaron propuestas.")
        print("=" * 120)
        return

    header = f"{'Origen':<20} {'Destino':<25} {'G1(Tiempo)':<12} {'G2(Legal)':<12} {'G3(Doc)':<10} {'G4(Id)':<10} {'Estado':<20}"
    print(header)
    print("-" * 120)
    for p in proposals:
        g1 = p.compuerta_1_continuidad.status.value
        g2 = p.compuerta_2_legal.status.value
        g3 = p.compuerta_3_estructura.status.value
        g4 = p.compuerta_4_identidad_destino.status.value
        status = p.status.value

        orig = (p.origen_entidad[:18] + "..") if len(p.origen_entidad) > 20 else p.origen_entidad
        dest = (p.destino_entidad[:23] + "..") if len(p.destino_entidad) > 25 else p.destino_entidad

        print(f"{orig:<20} {dest:<25} {g1:<12} {g2:<12} {g3:<10} {g4:<10} {status:<20}")

    print("=" * 120)
    resumen = {
        "PROPUESTA": sum(1 for p in proposals if p.status == ProposalStatus.PROPUESTA),
        "EVIDENCIA_INCOMPLETA": sum(1 for p in proposals if p.status == ProposalStatus.EVIDENCIA_INCOMPLETA),
        "RECHAZADA": sum(1 for p in proposals if p.status == ProposalStatus.RECHAZADA),
        "ERROR_DESCARGA": sum(1 for p in proposals if p.status == ProposalStatus.ERROR_DESCARGA),
        "ACEPTADA": sum(1 for p in proposals if p.status == ProposalStatus.ACEPTADA),
    }
    print(f"Resumen de estados: {resumen}")
    print("=" * 120)


def main():
    args = parse_args()
    evaluator = InheritanceEvaluator(output_dir=args.output.parent)
    candidates = load_candidates(args.input, evaluator)
    proposals = evaluator.evaluate_all(candidates)
    evaluator.save_proposals(proposals, args.output)
    print_report(proposals)


if __name__ == "__main__":
    main()
