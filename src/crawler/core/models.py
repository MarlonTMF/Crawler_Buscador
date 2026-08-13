"""
Modelos de dominio Pydantic v2 para la representación estructurada del prospector externo.
Alineado con el contrato JSON Schema 'ExternalSourceMap' v1.0.0 definido en document_project.md.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, HttpUrl


class SourceInfo(BaseModel):
    """Información general sobre la fuente externa rastreada."""
    id: str = Field(..., description="Identificador único de la fuente, ej. 'finrural'")
    name: str = Field(..., description="Nombre legible de la fuente, ej. 'FINRURAL'")
    base_url: str = Field(..., description="URL base oficial de la fuente")
    allowed_domains: List[str] = Field(default_factory=list, description="Dominios permitidos para el crawl")


class CrawlRunInfo(BaseModel):
    """Metadatos de la ejecución actual del crawler."""
    id: str = Field(..., description="Identificador único de la corrida de crawl")
    started_at: str = Field(..., description="Timestamp ISO 8601 de inicio")
    finished_at: str = Field(..., description="Timestamp ISO 8601 de finalización")
    status: Literal["success", "partial", "failed"] = Field(..., description="Estado de finalización del crawl")


class ResourceMetadata(BaseModel):
    """Metadatos de bajo costo obtenidos para un recurso descargable (Metadatos de Nivel 5)."""
    content_length_bytes: Optional[int] = Field(None, description="Tamaño del archivo en bytes si estuvo disponible por headers HTTP")
    sha256: Optional[str] = Field(None, description="Hash SHA-256 del contenido descargado para reconciliación anti-duplicidad")
    etag: Optional[str] = Field(None, description="Header HTTP ETag devuelto por el servidor")
    last_modified: Optional[str] = Field(None, description="Header HTTP Last-Modified en ISO 8601")
    date_extraction_method: str = Field("unknown", description="Método que determinó la fecha (url_pattern, dom_context, http_header, pdf_content)")
    date_confidence: Literal["high", "medium", "low", "unknown"] = Field("unknown", description="Nivel de confianza en la fecha extraída")
    geographic_coverage: List[str] = Field(default_factory=list, description="Cobertura geográfica asociada, ej. ['Bolivia']")
    entities: List[str] = Field(default_factory=list, description="Entidades/IFDs identificadas en el recurso")
    content_signature: Optional[str] = Field(None, description="Firma semántica compacta para optimizar consumo de tokens por IA")
    extracted_from_archive: Optional[str] = Field(None, description="URL del paquete comprimido de origen si este recurso fue extraído de un .zip/.tar")


class ResourceEvidence(BaseModel):
    """Trazabilidad del descubrimiento del recurso en el sitio de origen."""
    anchor_text: Optional[str] = Field(None, description="Texto del enlace HTML")
    context_text: Optional[str] = Field(None, description="Texto contextual alrededor del enlace")
    discovered_from: Optional[str] = Field(None, description="URL de la página donde se descubrió el enlace")
    extraction_methods: List[str] = Field(default_factory=list, description="Historial de técnicas aplicadas")


class ResourceItem(BaseModel):
    """Representa un archivo descargable concreto o activo documental."""
    id: str = Field(..., description="Resource key estable (ej. 'finrural:reporte_financiero_mensual:2026-01:pdf')")
    title: str = Field(..., description="Título o descripción del recurso")
    url_origin: str = Field(..., description="Página fuente donde se descubrió el recurso")
    download_url: str = Field(..., description="URL absoluta de descarga directa")
    canonical_url: str = Field(..., description="URL canónica sin parámetros de rastreo o cache-busting")
    file_type: str = Field(..., description="Extensión/formato detectado (pdf, xlsx, csv, etc.)")
    mime_type: Optional[str] = Field(None, description="Tipo MIME del recurso")
    period_start: Optional[str] = Field(None, description="Fecha de inicio del período de datos (YYYY-MM-DD)")
    period_end: Optional[str] = Field(None, description="Fecha de corte o último dato del período (YYYY-MM-DD)")
    published_at: Optional[str] = Field(None, description="Fecha de publicación en el sitio si se detectó")
    retrieved_at: str = Field(..., description="Timestamp ISO 8601 en que el crawler recuperó este recurso")
    metadata: ResourceMetadata = Field(default_factory=ResourceMetadata)
    evidence: ResourceEvidence = Field(default_factory=ResourceEvidence)


class DatasetItem(BaseModel):
    """Serie periódica de información identificada en la fuente."""
    id: str = Field(..., description="Identificador único del dataset, ej. 'reporte_financiero_mensual'")
    name: str = Field(..., description="Nombre del dataset")
    source_url: str = Field(..., description="URL índice del dataset")
    periodicity: Literal["monthly", "quarterly", "annual", "irregular", "unknown"] = Field("monthly", description="Periodicidad esperada")
    resources: List[ResourceItem] = Field(default_factory=list, description="Lista de recursos pertenecientes a este dataset")


class ChangeEventItem(BaseModel):
    """Evento de cambio o diagnóstico detectado frente a ejecuciones previas."""
    event_type: Literal["new_resource", "resource_missing", "url_changed", "content_changed", "duplicate_detected"]
    resource_id: str
    previous_url: Optional[str] = None
    current_url: Optional[str] = None
    detected_at: str


class ExternalSourceMap(BaseModel):
    """Contrato final estandarizado que emite el prospector externo al Motor de Conciliación."""
    schema_version: str = Field("1.0.0", description="Versión del contrato de datos")
    source: SourceInfo
    crawl_run: CrawlRunInfo
    datasets: List[DatasetItem] = Field(default_factory=list)
    change_events: List[ChangeEventItem] = Field(default_factory=list)
