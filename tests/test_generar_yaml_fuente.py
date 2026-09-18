"""
tests/test_generar_yaml_fuente.py — Pruebas unitarias para el generador de esqueletos YAML (B-12).
"""

import tempfile
from pathlib import Path
import pytest
import yaml

from scripts.generar_yaml_fuente import (
    clean_source_id,
    derive_domains,
    derive_base_url,
    find_source_record,
    is_headless_required,
    is_strapi_spa,
    build_yaml_skeleton,
    generate_yaml_for_source,
)
from crawler.sources.generic_adapter import GenericSourceAdapter


DIAGNOSTIC_PATH = Path("output/excel_urls_diagnostic.json")


def test_clean_source_id():
    assert clean_source_id("FINRURAL") == "finrural"
    assert clean_source_id("BCB_BRASIL") == "bcb_brasil"
    assert clean_source_id("DOLARBLUEBOLIVIA") == "dolarbluebolivia"
    assert clean_source_id("SPVS-APS") == "spvs_aps"


def test_derive_domains():
    assert derive_domains("https://www.finrural.org.bo/index.php") == ["www.finrural.org.bo", "finrural.org.bo"]
    assert derive_domains("https://bcb.gov.br/") == ["www.bcb.gov.br", "bcb.gov.br"]


def test_derive_base_url():
    assert derive_base_url("https://www.finrural.org.bo/subpage/file.pdf") == "https://www.finrural.org.bo"
    assert derive_base_url("http://ice.santacruz.gob.bo/repositorio") == "http://ice.santacruz.gob.bo"


def test_generar_yaml_finrural_structural_fidelity():
    """Verifica que el YAML generado para FINRURAL coincide estructuralmente con el escrito a mano."""
    record = find_source_record("FINRURAL", DIAGNOSTIC_PATH)
    assert record is not None, "FINRURAL debe existir en el diagnóstico"

    yaml_text, parsed = build_yaml_skeleton(record)

    # Cargar el YAML escrito a mano de referencia
    reference_path = Path("config/source_finrural.yaml")
    assert reference_path.exists()
    with open(reference_path, "r", encoding="utf-8") as f:
        ref = yaml.safe_load(f)

    # 1. Campos estructurales equivalentes
    assert parsed["source"]["id"] == ref["source"]["id"]
    assert parsed["source"]["base_url"] == ref["source"]["base_url"]
    assert set(parsed["source"]["allowed_domains"]) == set(ref["source"]["allowed_domains"])
    assert parsed["crawl"]["max_depth"] == ref["crawl"]["max_depth"]
    assert parsed["crawl"]["strategy"] == ref["crawl"]["strategy"]
    assert parsed["crawl"]["rate_limit_per_second"] == ref["crawl"]["rate_limit_per_second"]
    assert parsed["crawl"]["allowed_extensions"] == ref["crawl"]["allowed_extensions"]
    assert parsed["audit"]["enabled"] == ref["audit"]["enabled"]

    # 2. REGLA CRÍTICA: las reglas de clasificación van vacías con TODO
    assert parsed["classification"]["dataset_rules"] == []
    assert parsed["classification"]["excluded_path_keywords"] == []
    assert parsed["classification"]["document_path_tokens"] == []

    # Verificar que el texto contiene el TODO explícito
    assert "# TODO: completar tras explorar el sitio" in yaml_text


def test_generar_yaml_bcp_bcrp_headless_flag():
    """Verifica que BCP y BCRP nacen con la opción de navegador headless activada."""
    bcp_record = find_source_record("BCP", DIAGNOSTIC_PATH)
    assert bcp_record is not None
    assert is_headless_required(bcp_record) is True

    _, bcp_parsed = build_yaml_skeleton(bcp_record)
    assert bcp_parsed["crawl"]["use_playwright"] is True
    assert bcp_parsed["crawl"]["use_playwright_ocr"] is True
    assert bcp_parsed["crawl"]["headless"] is True

    bcrp_record = find_source_record("BCRP", DIAGNOSTIC_PATH)
    assert bcrp_record is not None
    assert is_headless_required(bcrp_record) is True

    _, bcrp_parsed = build_yaml_skeleton(bcrp_record)
    assert bcrp_parsed["crawl"]["use_playwright"] is True
    assert bcrp_parsed["crawl"]["use_playwright_ocr"] is True
    assert bcrp_parsed["crawl"]["headless"] is True


def test_generar_yaml_sicsantacruz_strapi_api():
    """Verifica que SICSANTACRUZ incluye la advertencia operativa de la API Strapi."""
    record = find_source_record("SICSANTACRUZ", DIAGNOSTIC_PATH)
    assert record is not None
    assert is_strapi_spa(record) is True

    yaml_text, parsed = build_yaml_skeleton(record)
    assert parsed["source"]["id"] == "sicsantacruz"
    assert "/api/estudios" in yaml_text
    assert "backend Strapi" in yaml_text


def test_generic_source_adapter_compatibility():
    """Verifica que el GenericSourceAdapter puede cargar el esqueleto sin errores."""
    record = find_source_record("FINRURAL", DIAGNOSTIC_PATH)
    yaml_text, _ = build_yaml_skeleton(record)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_yaml = Path(tmpdir) / "source_test.yaml"
        tmp_yaml.write_text(yaml_text, encoding="utf-8")

        adapter = GenericSourceAdapter(tmp_yaml)
        assert adapter.source_id == "finrural"
        assert adapter.base_url == "https://www.finrural.org.bo"
        assert adapter.allowed_domains == ["www.finrural.org.bo", "finrural.org.bo"]
        assert adapter.allowed_extensions == ["pdf", "xlsx", "xls", "csv", "zip"]
        assert adapter.rate_limit == 1.0
        assert adapter.is_url_excluded("https://www.finrural.org.bo/cualquier-ruta") is False
        assert adapter.classify_dataset("https://www.finrural.org.bo/doc.pdf") == "documentos_publicos"


def test_overwrite_protection_without_force():
    """Verifica que no se sobreescribe un archivo existente a menos que se use force=True."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        existing = out_dir / "source_finrural.yaml"
        existing.write_text("# Contenido original manual", encoding="utf-8")

        with pytest.raises(FileExistsError):
            generate_yaml_for_source(
                fuente="FINRURAL",
                diagnostic_path=DIAGNOSTIC_PATH,
                output_dir=out_dir,
                force=False,
            )

        # Con force=True debe proceder
        path = generate_yaml_for_source(
            fuente="FINRURAL",
            diagnostic_path=DIAGNOSTIC_PATH,
            output_dir=out_dir,
            force=True,
        )
        assert path == existing
        assert "Esqueleto autogenerado" in existing.read_text(encoding="utf-8")
