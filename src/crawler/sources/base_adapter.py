"""
Interfaz abstracta BaseSourceAdapter para adaptadores de fuente declarativos.
Cualquier nueva fuente (ej. BCB, ASFI) implementará esta interfaz.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import yaml
from pathlib import Path


class BaseSourceAdapter(ABC):
    """Clase base abstracta para definir las reglas y configuraciones de una fuente."""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Archivo de configuración no encontrado: {self.config_path}")
        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @property
    def source_id(self) -> str:
        return self.config["source"]["id"]

    @property
    def source_name(self) -> str:
        return self.config["source"]["name"]

    @property
    def base_url(self) -> str:
        return self.config["source"]["base_url"]

    @property
    def allowed_domains(self) -> List[str]:
        return self.config["source"].get("allowed_domains", [])

    @property
    def seeds(self) -> List[str]:
        return self.config["crawl"].get("seeds", [])

    @property
    def allowed_extensions(self) -> List[str]:
        return self.config["crawl"].get("allowed_extensions", ["pdf", "xlsx", "xls", "csv"])

    @property
    def rate_limit(self) -> float:
        return self.config["crawl"].get("rate_limit_per_second", 1.0)

    @property
    def drop_query_params(self) -> List[str]:
        return self.config.get("canonicalization", {}).get("drop_query_parameters", [])

    @property
    def use_playwright(self) -> bool:
        crawl_cfg = self.config.get("crawl", {})
        return bool(crawl_cfg.get("use_playwright", False) or crawl_cfg.get("headless", False))

    @abstractmethod
    def is_url_excluded(self, url: str) -> bool:
        """Determina si una URL debe ser ignorada según reglas de exclusión de la fuente."""
        pass

    @abstractmethod
    def classify_dataset(self, url: str, anchor_text: str = "") -> Optional[str]:
        """Asigna un ID de dataset a partir de la URL y/o texto contextual."""
        pass
