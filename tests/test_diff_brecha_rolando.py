"""
tests/test_diff_brecha_rolando.py
==================================
Pruebas unitarias para scripts/diff_brecha_rolando.py (B-41).
"""

import json
from pathlib import Path
import pytest
from scripts.diff_brecha_rolando import (
    extraer_recursos_rolando,
    normalizar_url_comparacion,
    analizar_portal,
)


def test_normalizar_url_comparacion():
    u1 = "HTTPS://WWW.ASFI.GOB.BO/Sites/default/files/test.zip "
    norm = normalizar_url_comparacion(u1)
    assert norm == "https://www.asfi.gob.bo/Sites/default/files/test.zip"


def test_extraer_recursos_rolando(tmp_path):
    sample_data = {
        "CATEGORIA": {
            "subcat": [
                {
                    "descripcion": "Doc 1",
                    "url_descarga": "https://example.com/doc1.pdf",
                    "tipo_archivo": "PDF"
                }
            ],
            "item_directo": {
                "descripcion": "Doc 2",
                "url_descarga": "https://example.com/doc2.xlsx",
                "tipo_archivo": "XLSX"
            }
        }
    }
    json_file = tmp_path / "rolando_sample.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(sample_data, f)

    recursos = extraer_recursos_rolando(json_file)
    assert len(recursos) == 2
    urls = [r["url_descarga"] for r in recursos]
    assert "https://example.com/doc1.pdf" in urls
    assert "https://example.com/doc2.xlsx" in urls
