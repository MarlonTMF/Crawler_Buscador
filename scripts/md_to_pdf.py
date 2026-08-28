"""Simple Markdown to PDF converter using ReportLab.

This script renders a Markdown file into a plain PDF suitable for stakeholder sharing.
It does a basic conversion: strips Markdown and writes paragraphs. For a prettier PDF
use pandoc or wkhtmltopdf; this is a minimal local fallback that doesn't require extra binaries.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
import sys


def md_to_text(md: str) -> str:
    # Very small Markdown -> plain text conversion
    lines = []
    for raw in md.splitlines():
        s = raw.strip()
        if s.startswith('#'):
            # header: make uppercase
            s = s.lstrip('#').strip().upper()
        lines.append(s)
    return '\n'.join(lines)


def render_pdf(text: str, out_path: str):
    c = canvas.Canvas(out_path, pagesize=A4)
    width, height = A4
    margin = 20 * mm
    x = margin
    y = height - margin
    line_height = 10
    for paragraph in text.split('\n'):
        if not paragraph:
            y -= line_height
            if y < margin:
                c.showPage(); y = height - margin
            continue
        # wrap simple
        words = paragraph.split(' ')
        line = ''
        for w in words:
            test = (line + ' ' + w).strip()
            if c.stringWidth(test, 'Helvetica', 10) > (width - margin * 2):
                c.drawString(x, y, line)
                y -= line_height
                line = w
                if y < margin:
                    c.showPage(); y = height - margin
            else:
                line = test
        if line:
            c.drawString(x, y, line)
            y -= line_height
        if y < margin:
            c.showPage(); y = height - margin
    c.save()


def main():
    if len(sys.argv) < 3:
        print('Usage: md_to_pdf.py input.md output.pdf')
        sys.exit(2)
    md_path = sys.argv[1]
    out_pdf = sys.argv[2]
    with open(md_path, 'r', encoding='utf-8') as f:
        md = f.read()
    text = md_to_text(md)
    render_pdf(text, out_pdf)
    print('Written', out_pdf)


if __name__ == '__main__':
    main()
