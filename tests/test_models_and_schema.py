"""
Pruebas unitarias para modelos Pydantic v2 y validación de JSON Schema.
"""

import pytest
from pathlib import Path
from crawler.core.models import (
    SourceInfo, CrawlRunInfo, ResourceMetadata, ResourceEvidence,
    ResourceItem, DatasetItem, ExternalSourceMap
)
from crawler.validators.schema_validator import SchemaValidator


def test_models_and_schema_validation():
    source_info = SourceInfo(
        id="finrural",
        name="FINRURAL",
        base_url="https://www.finrural.org.bo",
        allowed_domains=["www.finrural.org.bo"]
    )
    crawl_info = CrawlRunInfo(
        id="crawl_test_123",
        started_at="2026-08-10T11:00:00Z",
        finished_at="2026-08-10T11:00:05Z",
        status="success"
    )

    resource = ResourceItem(
        id="finrural:reporte_financiero_mensual:2026-01:pdf",
        title="Información Financiera Enero 2026",
        url_origin="https://www.finrural.org.bo/reporte-financiero-mensual/",
        download_url="https://www.finrural.org.bo/archivos/info_financiera/2026/financiera_01_2026.pdf",
        canonical_url="https://www.finrural.org.bo/archivos/info_financiera/2026/financiera_01_2026.pdf",
        file_type="pdf",
        period_start="2026-01-01",
        period_end="2026-01-31",
        retrieved_at="2026-08-10T11:00:05Z",
        metadata=ResourceMetadata(
            content_length_bytes=1048576,
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            date_extraction_method="url_pattern",
            date_confidence="high"
        ),
        evidence=ResourceEvidence(
            anchor_text="Enero 2026",
            context_text="Reporte Enero 2026"
        )
    )

    dataset = DatasetItem(
        id="reporte_financiero_mensual",
        name="Reporte Financiero Mensual",
        source_url="https://www.finrural.org.bo/reporte-financiero-mensual/",
        periodicity="monthly",
        resources=[resource]
    )

    source_map = ExternalSourceMap(
        schema_version="1.0.0",
        source=source_info,
        crawl_run=crawl_info,
        datasets=[dataset],
        change_events=[]
    )

    data = source_map.model_dump(mode="json")
    validator = SchemaValidator()
    is_valid, err_msg = validator.validate(data)

    assert is_valid is True, f"Validación de JSON Schema falló: {err_msg}"
