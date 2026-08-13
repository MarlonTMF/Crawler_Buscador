"""
Pruebas unitarias para el extractor de archivos comprimidos (ArchiveExtractor).
"""

import io
import zipfile
import pytest
from crawler.core.archive_extractor import ArchiveExtractor, ExtractedFileItem


def create_sample_zip_bytes() -> bytes:
    """Crea un buffer ZIP en memoria con dos archivos de prueba (PDF y TXT)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("reporte_financiero_01_2026.pdf", b"%PDF-1.4 Mock PDF Content")
        zf.writestr("notas_explicativas.txt", b"Texto de notas explicativas")
        zf.writestr("subfolder/resumen_2026.xlsx", b"Mock Excel Content")
    return buf.getvalue()


def test_is_archive_extension():
    assert ArchiveExtractor.is_archive_extension("zip") is True
    assert ArchiveExtractor.is_archive_extension("tar") is True
    assert ArchiveExtractor.is_archive_extension("tgz") is True
    assert ArchiveExtractor.is_archive_extension("pdf") is False
    assert ArchiveExtractor.is_archive_extension("xlsx") is False


def test_extract_zip_contents():
    extractor = ArchiveExtractor()
    zip_bytes = create_sample_zip_bytes()

    # Extraer solo PDF y XLSX
    extracted = extractor.extract_archive(
        content_bytes=zip_bytes,
        archive_name="reportes_2026.zip",
        allowed_extensions=["pdf", "xlsx"]
    )

    assert len(extracted) == 2
    filenames = [item.inner_filename for item in extracted]
    assert "reporte_financiero_01_2026.pdf" in filenames
    assert "resumen_2026.xlsx" in filenames
    assert "notas_explicativas.txt" not in filenames


def test_extracted_file_item_hashes():
    extractor = ArchiveExtractor()
    zip_bytes = create_sample_zip_bytes()

    extracted = extractor.extract_archive(
        content_bytes=zip_bytes,
        archive_name="reportes_2026.zip",
        allowed_extensions=["pdf"]
    )

    assert len(extracted) == 1
    pdf_item = extracted[0]
    assert pdf_item.file_type == "pdf"
    assert pdf_item.size_bytes > 0
    assert len(pdf_item.sha256) == 64  # SHA-256 hex string length
