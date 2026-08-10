"""
Validador de esquema JSON Schema para garantizar el cumplimiento estricto del contrato ExternalSourceMap.
"""

import json
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import jsonschema


class SchemaValidator:
    """Clase encargada de validar diccionarios JSON contra el esquema formal JSON Schema."""

    def __init__(self, schema_path: Optional[Path] = None):
        if schema_path is None:
            # Resolviendo desde src/crawler/validators/schema_validator.py -> crawler_finrural/schemas/source-map.schema.json
            schema_path = Path(__file__).resolve().parents[3] / "schemas" / "source-map.schema.json"
        
        self.schema_path = schema_path
        self._schema_data = self._load_schema()

    def _load_schema(self) -> Dict[str, Any]:
        """Carga el esquema desde el archivo JSON."""
        if not self.schema_path.exists():
            raise FileNotFoundError(f"No se encontró el archivo de esquema en: {self.schema_path}")
        with open(self.schema_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def validate(self, instance: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Valida una instancia JSON.
        
        Returns:
            Tuple[bool, Optional[str]]: (True, None) si es válido, (False, "mensaje de error") si falla.
        """
        try:
            jsonschema.validate(instance=instance, schema=self._schema_data)
            return True, None
        except jsonschema.exceptions.ValidationError as err:
            return False, f"Error de validación de esquema en '{err.json_path}': {err.message}"
        except Exception as err:
            return False, f"Error inesperado durante la validación: {str(err)}"
