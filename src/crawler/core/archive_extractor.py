"""
Extractor de archivos comprimidos (.zip, .tar, .tar.gz, .tgz, .bz2).
Permite descomprimir archivos en memoria y extraer sus documentos contenidos (.pdf, .xlsx, .csv, etc.).
"""

import io
import zipfile
import tarfile
import hashlib
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class ExtractedFileItem:
    """Representa un archivo extraído individualmente desde un contenedor comprimido."""

    def __init__(self, inner_filename: str, file_type: str, content_bytes: bytes):
        self.inner_filename = inner_filename
        self.file_type = file_type.lower()
        self.content_bytes = content_bytes
        self.size_bytes = len(content_bytes)
        self.sha256 = hashlib.sha256(content_bytes).hexdigest()


class ArchiveExtractor:
    """Procesador de archivos comprimidos en memoria."""

    ARCHIVE_EXTENSIONS = {"zip", "tar", "gz", "tgz", "bz2", "rar", "7z"}

    @classmethod
    def is_archive_extension(cls, ext: str) -> bool:
        """Verifica si la extensión corresponde a un formato comprimido soportado."""
        return ext.lower().strip(".") in cls.ARCHIVE_EXTENSIONS

    @staticmethod
    def _detect_extension(filename: str) -> str:
        """Detecta la extensión de un archivo interno."""
        if "." in filename:
            return filename.rsplit(".", 1)[1].lower()
        return "bin"

    def extract_zip(self, content_bytes: bytes, allowed_extensions: List[str]) -> List[ExtractedFileItem]:
        """Extrae archivos internos desde un buffer ZIP."""
        extracted: List[ExtractedFileItem] = []
        allowed_set = {ext.lower().strip(".") for ext in allowed_extensions}

        try:
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
                for member_name in zf.namelist():
                    # Ignorar directorios y archivos de sistema (Mac / Windows)
                    if member_name.endswith("/") or "__MACOSX" in member_name or member_name.startswith("."):
                        continue

                    ext = self._detect_extension(member_name)
                    if allowed_set and ext not in allowed_set:
                        continue

                    try:
                        file_bytes = zf.read(member_name)
                        clean_name = member_name.split("/")[-1]
                        if clean_name:
                            extracted.append(ExtractedFileItem(clean_name, ext, file_bytes))
                    except Exception as err:
                        logger.warning(f"No se pudo extraer '{member_name}' del ZIP: {err}")

        except Exception as err:
            logger.error(f"Error al abrir el archivo ZIP: {err}")

        return extracted

    def extract_tar(self, content_bytes: bytes, allowed_extensions: List[str]) -> List[ExtractedFileItem]:
        """Extrae archivos internos desde un buffer TAR/TAR.GZ."""
        extracted: List[ExtractedFileItem] = []
        allowed_set = {ext.lower().strip(".") for ext in allowed_extensions}

        try:
            with tarfile.open(fileobj=io.BytesIO(content_bytes)) as tf:
                for member in tf.getmembers():
                    if member.isdir() or "__MACOSX" in member.name or member.name.startswith("."):
                        continue

                    ext = self._detect_extension(member.name)
                    if allowed_set and ext not in allowed_set:
                        continue

                    try:
                        f = tf.extractfile(member)
                        if f:
                            file_bytes = f.read()
                            clean_name = member.name.split("/")[-1]
                            if clean_name:
                                extracted.append(ExtractedFileItem(clean_name, ext, file_bytes))
                    except Exception as err:
                        logger.warning(f"No se pudo extraer '{member.name}' del TAR: {err}")

        except Exception as err:
            logger.error(f"Error al abrir el archivo TAR: {err}")

        return extracted

    def extract_archive(
        self,
        content_bytes: bytes,
        archive_name: str,
        allowed_extensions: List[str]
    ) -> List[ExtractedFileItem]:
        """
        Punto de entrada principal para extraer cualquier tipo de comprimido reconocido.
        
        Returns:
            List[ExtractedFileItem]: Lista de archivos extraídos válidos.
        """
        ext = self._detect_extension(archive_name)

        if ext == "zip":
            return self.extract_zip(content_bytes, allowed_extensions)
        elif ext in ["tar", "gz", "tgz", "bz2"]:
            return self.extract_tar(content_bytes, allowed_extensions)
        else:
            # Intento de fallback automático ZIP
            try:
                return self.extract_zip(content_bytes, allowed_extensions)
            except Exception:
                logger.warning(f"Formato de compresión de '{archive_name}' no soportado directamente.")
                return []
