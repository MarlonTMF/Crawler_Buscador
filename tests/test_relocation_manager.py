"""
tests/test_relocation_manager.py
================================
Pruebas unitarias para RelocationManager (resolución de archivos movidos y herencia).
"""

from pathlib import Path
import json
import pytest

from crawler.core.relocation_manager import RelocationManager


def test_relocation_manager_loads_moved_urls(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    moved_file = config_dir / "moved_urls.json"
    
    mock_data = [
        {
            "original": "https://www.cadexco.org.bo",
            "resolved": "https://cadexco.bo/",
            "confidence": 0.9,
            "reason": "Dominio migrado",
            "matched_keywords": ["cochabamba"]
        },
        {
            "original": "https://www.aduana.gob.bo/aduana7/content/boletin",
            "resolved": "https://www.aduana.gob.bo/com_boletines",
            "confidence": 0.75,
            "reason": "Migracion de plataforma",
            "matched_keywords": ["boletin"]
        },
        {
            "original": "https://www.imf.org",
            "resolved": None,
            "confidence": 0.0,
            "reason": "Revertido 403",
            "matched_keywords": []
        }
    ]
    moved_file.write_text(json.dumps(mock_data), encoding="utf-8")
    
    rm = RelocationManager(config_dir=config_dir)
    
    # 1. Exact match
    res_exact = rm.get_moved_mapping("https://www.cadexco.org.bo")
    assert res_exact is not None
    assert res_exact["resolved"] == "https://cadexco.bo/"
    
    # 2. Prefix match
    res_prefix = rm.get_moved_mapping("https://www.aduana.gob.bo/aduana7/content/boletin/2023.pdf")
    assert res_prefix is not None
    assert res_prefix["resolved"] == "https://www.aduana.gob.bo/com_boletines"
    
    # 3. None for zero confidence or null resolved
    res_null = rm.get_moved_mapping("https://www.imf.org")
    assert res_null is None


def test_is_authorized_successor():
    rm = RelocationManager()
    
    # Mismo dominio
    assert rm.is_authorized_successor("bcb.gob.bo", "bcb.gob.bo")
    assert rm.is_authorized_successor("bcb.gob.bo", "www.bcb.gob.bo")
    assert rm.is_authorized_successor("bcb.gob.bo", "deudaexterna.bcb.gob.bo")
    
    # Sucesores canónicos
    assert rm.is_authorized_successor("spvs.gob.bo", "asfi.gob.bo")
    assert rm.is_authorized_successor("spvs.gob.bo", "www.aps.gob.bo")
    assert rm.is_authorized_successor("sbef.gob.bo", "asfi.gob.bo")
    assert rm.is_authorized_successor("suptrans.gob.bo", "att.gob.bo")
    assert rm.is_authorized_successor("fundempresa.org.bo", "seprec.gob.bo")
    
    # Dominio no autorizado o no relacionado
    assert not rm.is_authorized_successor("bcb.gob.bo", "sitio-malicioso.com")
    assert not rm.is_authorized_successor("spvs.gob.bo", "ine.gob.bo")


def test_translate_url_to_successor():
    rm = RelocationManager()
    
    old_url = "https://www.spvs.gob.bo/archivos/memoria_2015.pdf"
    candidates = rm.translate_url_to_successor(old_url)
    
    assert len(candidates) > 0
    # Debe contener traducciones a asfi y aps
    assert any("asfi.gob.bo" in c for c in candidates)
    assert any("aps.gob.bo" in c for c in candidates)
    assert any("/spvs/" in c or "/docs/" in c for c in candidates)


def test_generate_path_variants():
    rm = RelocationManager()
    
    url = "https://www.bcb.gob.bo/archivos/depex_jun_2023.pdf"
    variants = rm.generate_path_variants(url, period="2023-S1")
    
    assert len(variants) > 0
    # Guiones en lugar de guiones bajos
    assert any("depex-jun-2023.pdf" in v or "depex%20jun%202023.pdf" in v for v in variants)
    # Variación de carpeta
    assert any("/docs/" in v or "/descargas/" in v or "/webdocs/" in v for v in variants)
    # Variación de año 2 dígitos
    assert any("23.pdf" in v for v in variants)


def test_follow_redirect_authorized(monkeypatch):
    rm = RelocationManager()

    class MockResponse:
        def __init__(self, url, status_code, history=None):
            self.url = url
            self.status_code = status_code
            self.history = history or []
            self.headers = {"Content-Type": "application/pdf", "Content-Length": "12345"}

    class MockSession:
        def head(self, url, **kwargs):
            if "spvs.gob.bo" in url:
                # Redirect to authorized successor asfi.gob.bo
                return MockResponse("https://www.asfi.gob.bo/docs/spvs_memoria_2015.pdf", 200, history=[1])
            elif "malicious" in url:
                # Redirect to malicious non-authorized domain
                return MockResponse("https://phishing.com/stolen.pdf", 200, history=[1])
            return MockResponse(url, 200)

    sess = MockSession()
    # 1. Redirección hacia sucesor autorizado
    res = rm.follow_redirect("https://www.spvs.gob.bo/archivos/memoria_2015.pdf", session=sess)
    assert res["redirected"] is True
    assert res["final_url"] == "https://www.asfi.gob.bo/docs/spvs_memoria_2015.pdf"
    assert res["is_authorized"] is True

    # 2. Redirección hacia sitio no autorizado
    res_bad = rm.follow_redirect("https://malicious.spvs.gob.bo/file.pdf", session=sess)
    assert res_bad["redirected"] is True
    assert res_bad["is_authorized"] is False

