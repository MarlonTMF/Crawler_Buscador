"""
Punto de entrada ejecutable CLI para el prospector externo.
Soporta múltiples fuentes (FINRURAL, Bolsa Boliviana de Valores BBV, ASFI, etc.).
"""

import sys
import argparse
import logging
from pathlib import Path
import yaml

# Asegurar que 'src' esté en el PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.sources.finrural_adapter import FinruralAdapter
from crawler.sources.bbv_adapter import BbvAdapter
from crawler.sources.generic_adapter import GenericSourceAdapter
from crawler.core.orchestrator import CrawlOrchestrator


def setup_logging(verbose: bool = False) -> None:
    """Configura el registro de logs en consola."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def load_adapter(config_path: Path):
    """Carga dinámicamente el adaptador adecuado según el archivo de configuración YAML."""
    if not config_path.exists():
        raise FileNotFoundError(f"Archivo de configuración no encontrado en: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    source_id = data.get("source", {}).get("id", "").lower()

    if source_id == "bbv":
        return BbvAdapter(config_path=config_path)
    elif source_id == "finrural":
        return FinruralAdapter(config_path=config_path)
    else:
        # Fallback para adaptadores declarativos genéricos
        return GenericSourceAdapter(config_path=config_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prospector Externo y Crawler de Fuentes Financieras (FINRURAL, BBV, ASFI) — Equipo 1 DataX"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(Path(__file__).resolve().parents[2] / "config" / "source_finrural.yaml"),
        help="Ruta al archivo de configuración YAML de la fuente (ej. config/source_bbv.yaml)"
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
    config_path = Path(args.config)
    output_dir = Path(args.output_dir)

    adapter = load_adapter(config_path)
    logger.info(f"=== Iniciando Prospector Externo para [{adapter.source_name}] ===")

    orchestrator = CrawlOrchestrator(adapter=adapter, output_dir=output_dir)

    try:
        source_map = orchestrator.run()
        total_resources = sum(len(ds.resources) for ds in source_map.datasets)
        logger.info(f"=== Prospección finalizada con éxito ===")
        logger.info(f"Fuente: {source_map.source.name} | Datasets: {len(source_map.datasets)} | Recursos procesados: {total_resources}")
        logger.info(f"Archivos exportados en: {orchestrator.source_output_dir.resolve()}")
    except Exception as e:
        logger.critical(f"Error fatal durante la prospección: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
