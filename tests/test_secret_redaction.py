"""Regresion: ningun texto registrado puede arrastrar la clave de API.

La clave anterior del proyecto terminó publicada en
``output/url_resolution_log.json`` porque el texto de una excepción de
``requests`` incluye la URL completa de la petición, y esa URL lleva
``?key=<GEMINI_API_KEY>``. El valor viajaba dentro del campo ``reason`` del
veredicto de Gemini.
"""

import pytest

from crawler.core.fetcher import _redact_secrets

CLAVE_FALSA = "AIzaSyDUMMYKEY0123456789abcdefghijklmno"


def test_redacta_clave_en_query_string():
    texto = (
        "HTTPSConnectionPool(host='generativelanguage.googleapis.com', port=443): "
        f"Max retries exceeded with url: /v1beta/models/gemini-3.6-flash:generateContent?key={CLAVE_FALSA}"
    )
    limpio = _redact_secrets(texto)
    assert CLAVE_FALSA not in limpio
    assert "key=" in limpio  # se conserva la forma del error, solo se tapa el valor


def test_redacta_clave_suelta_sin_query_string():
    limpio = _redact_secrets(f"La consulta falló usando {CLAVE_FALSA} como credencial")
    assert CLAVE_FALSA not in limpio


def test_redacta_token_con_prefijo_aq():
    token = "AQ.Ab8RN6" + "X" * 44
    limpio = _redact_secrets(f"Authorization: Bearer {token}")
    assert token not in limpio


def test_no_altera_texto_sin_secretos():
    texto = "Gemini no devolvió respuesta útil para https://www.asfi.gob.bo/memoria.pdf"
    assert _redact_secrets(texto) == texto


def test_tolera_entradas_no_texto():
    assert _redact_secrets(None) is None
    assert _redact_secrets(123) == 123
