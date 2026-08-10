"""
Punto de entrada ejecutable CLI para el prospector externo FINRURAL.
"""

import sys
import argparse
import logging
from pathlib import Path

# Asegurar que 'src' esté en el PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.sources.finrural_adapter import FinruralAdapter
from crawler.core.orchestrator import CrawlOrchestrator


def setup_logging(verbose: bool = False) -> None:
    """Configura el registro de logs en consola."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prospector Externo y Crawler de Fuentes Financieras (FINRURAL) — Equipo 1 DataX"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(Path(__file__).resolve().parents[2] / "config" / "source_finrural.yaml"),
        help="Ruta al archivo de configuración YAML de la fuente"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(Path(__file__).resolve().parents[2] / "output"),
        help="Directorio de destino para los archivos JSON generados"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Habilita el modo de log detallado (DEBUG)"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    logger = logging.getLogger("crawler.main")
    logger.info("=== Iniciando Prospector Externo FINRURAL ===")

    config_path = Path(args.config)
    output_dir = Path(args.output_dir)

    adapter = FinruralAdapter(config_path=config_path)
    orchestrator = CrawlOrchestrator(adapter=adapter, output_dir=output_dir)

    try:
        source_map = orchestrator.run()
        total_resources = sum(len(ds.resources) for ds in source_map.datasets)
        logger.info(f"=== Prospección finalizada con éxito ===")
        logger.info(f"Fuente: {source_map.source.name} | Datasets: {len(source_map.datasets)} | Recursos procesados: {total_resources}")
        logger.info(f"Archivos exportados en: {output_dir.resolve()}")
    except Exception as e:
        logger.critical(f"Error fatal durante la prospección: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
