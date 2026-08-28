import os
from pathlib import Path
import pytest

from crawler.core.renderer_playwright import PlaywrightRenderer
from crawler.core.ocr_adapter import image_to_text


def test_playwright_screenshot_and_optional_ocr(tmp_path: Path):
    renderer = PlaywrightRenderer(headless=True)
    if not renderer.available():
        pytest.skip("Playwright not installed")

    html_file = tmp_path / "test.html"
    html_file.write_text("<html><body><h1 style='font-size:72px'>HELLO OCR</h1></body></html>")

    out_png = tmp_path / "out.png"
    ok = renderer.screenshot(html_file.as_uri(), str(out_png))
    assert ok, "Renderer failed to produce a screenshot"
    assert out_png.exists()

    # Try OCR only if pytesseract is available and Tesseract binary is present
    try:
        import pytesseract  # type: ignore
    except Exception:
        pytest.skip("pytesseract not installed")

    text = image_to_text(str(out_png))
    if text is None:
        pytest.skip("Tesseract binary not available or OCR failed")

    assert "HELLO" in text.upper()
