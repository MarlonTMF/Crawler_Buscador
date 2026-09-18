"""Genera un PDF con formato real (tabla, tipografía, colores) para el reporte de APIs.

A diferencia de ``scripts/md_to_pdf.py`` (que solo vuelca texto plano y no sabe
renderizar tablas Markdown), este módulo arma el PDF directamente a partir de los
datos estructurados usando ``reportlab.platypus``, así que las tablas salen como
tablas de verdad, con celdas, encabezados y ajuste de línea.
"""

from __future__ import annotations

from xml.sax.saxutils import escape as _xml_escape
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether, HRFlowable,
)

# Paleta alineada con el reporte HTML interactivo (radar_apis.html): navy institucional
# + ocre como color de "hallazgo". Se guarda también el string hex plano porque
# Color.hexval() de reportlab devuelve "0xrrggbb", que <font color="..."> no interpreta.
INK_HEX, INK = "#161B22", colors.HexColor("#161B22")
INK_2_HEX, INK_2 = "#4C5560", colors.HexColor("#4C5560")
INK_3_HEX, INK_3 = "#7B8390", colors.HexColor("#7B8390")
ACCENT_HEX, ACCENT = "#2E4B7A", colors.HexColor("#2E4B7A")
FOUND_HEX, FOUND = "#9C6A1E", colors.HexColor("#9C6A1E")
FOUND_SOFT = colors.HexColor("#F3E6C8")
MUTED_SOFT = colors.HexColor("#ECEDEF")
LINE = colors.HexColor("#D7DBCF")
SURFACE_2 = colors.HexColor("#F5F6F1")

def esc(s: Any) -> str:
    """Escapa texto dinámico antes de insertarlo en un Paragraph (que interpreta XML)."""
    return _xml_escape(str(s) if s is not None else "")


SOURCE_LABEL = {
    "probe": "sondeo", "subdomain": "subdominio", "js-bundle": "bundle JS",
    "network": "tráfico red", "link": "enlace",
}


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK),
        "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=10, leading=14, textColor=INK_2),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=INK, spaceBefore=14, spaceAfter=6),
        "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=INK),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=12.5, textColor=INK, alignment=TA_LEFT),
        "body_muted": ParagraphStyle("body_muted", fontName="Helvetica-Oblique", fontSize=9, leading=12.5, textColor=INK_3),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK),
        "cell_bold": ParagraphStyle("cell_bold", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=INK),
        "mono": ParagraphStyle("mono", fontName="Courier", fontSize=8, leading=11, textColor=INK),
        "kpi_num": ParagraphStyle("kpi_num", fontName="Helvetica-Bold", fontSize=22, leading=24, textColor=INK, alignment=1),
        "kpi_label": ParagraphStyle("kpi_label", fontName="Helvetica", fontSize=8, leading=10, textColor=INK_2, alignment=1),
    }


def _summary_table(total: int, with_api: int, with_docs: int, st: dict) -> Table:
    def tile(num, label, highlight=False):
        color_hex = FOUND_HEX if highlight else INK_HEX
        return [
            Paragraph(f'<font color="{color_hex}">{num}</font>', st["kpi_num"]),
            Paragraph(label, st["kpi_label"]),
        ]

    data = [[
        tile(total, "Dominios analizados"),
        tile(with_api, "Con API detectada", highlight=True),
        tile(with_docs, "Con documentación pública"),
    ]]
    # Cada celda recibe una mini-tabla interna de 2 filas para apilar número + etiqueta.
    wrapped = [[Table([[c[0]], [c[1]]], colWidths=[56 * mm]) for c in data[0]]]
    t = Table(wrapped, colWidths=[56 * mm, 56 * mm, 56 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _overview_table(results: list[dict[str, Any]], st: dict) -> Table:
    header = ["Fuente", "Institución", "API", "Endpoints", "Documentación"]
    rows = [[Paragraph(f"<b>{h}</b>", st["cell_bold"]) for h in header]]
    for r in results:
        rows.append([
            Paragraph(esc(r["fuente"]), st["cell"]),
            Paragraph(esc(r.get("institucion") or r["base_url"]), st["cell"]),
            Paragraph("Sí" if r["has_api"] else "No", st["cell"]),
            Paragraph(str(len(r["endpoints"])), st["cell"]),
            Paragraph("Sí" if r["has_documentation"] else "No", st["cell"]),
        ])

    t = Table(rows, colWidths=[24 * mm, 78 * mm, 14 * mm, 20 * mm, 30 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for i, r in enumerate(results, start=1):
        if r["has_api"]:
            style.append(("BACKGROUND", (0, i), (-1, i), FOUND_SOFT))
        elif i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), SURFACE_2))
    t.setStyle(TableStyle(style))
    return t


def _detail_block(r: dict[str, Any], st: dict):
    flow = [Paragraph(f"{esc(r['fuente'])} — {esc(r.get('institucion') or r['base_url'])}", st["h3"])]
    flow.append(Paragraph(esc(r["base_url"]), st["mono"]))
    flow.append(Spacer(1, 3))

    if r["has_api"]:
        for e in r["endpoints"]:
            tag = esc(SOURCE_LABEL.get(e.get("source"), e.get("source", "")))
            ct = f" · {esc(e['content_type'])}" if e.get("content_type") else ""
            flow.append(Paragraph(f'<font color="{ACCENT_HEX}">[{tag}]</font> {esc(e["url"])}{ct}', st["mono"]))
    else:
        flow.append(Paragraph("No se detectó ninguna API en este sitio con los métodos usados.", st["body_muted"]))

    if r["has_documentation"]:
        for d in r["documentation"]:
            flow.append(Paragraph(f'<font color="{FOUND_HEX}">[doc]</font> {esc(d["url"])}', st["mono"]))
    else:
        flow.append(Paragraph("Sin documentación de API pública (Swagger/OpenAPI/WSDL).", st["body_muted"]))

    flow.append(Spacer(1, 8))
    flow.append(HRFlowable(width="100%", thickness=0.4, color=LINE))
    flow.append(Spacer(1, 8))
    return flow


def render_api_report_pdf(results: list[dict[str, Any]], generated_at: str, out_path: str) -> None:
    st = _styles()
    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        topMargin=20 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title="Radar de APIs institucionales",
    )

    total = len(results)
    with_api = sum(1 for r in results if r["has_api"])
    with_docs = sum(1 for r in results if r["has_documentation"])

    story = []
    story.append(Paragraph("Radar de APIs institucionales", st["title"]))
    story.append(Paragraph(
        f"Generado {generated_at} · Prospección web DataX · barrido de {total} dominios únicos del "
        "inventario de fuentes para detectar APIs públicas y su documentación.",
        st["subtitle"],
    ))
    story.append(Spacer(1, 12))
    story.append(_summary_table(total, with_api, with_docs, st))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Resumen por institución", st["h2"]))
    story.append(_overview_table(results, st))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Filas resaltadas: sitios con API detectada. “API” aquí incluye tanto endpoints propios "
        "como APIs REST estándar del CMS (p. ej. wp-json de WordPress).",
        st["body_muted"],
    ))

    story.append(Spacer(1, 4))
    story.append(Paragraph("Detalle por institución", st["h2"]))
    ordered = sorted(results, key=lambda r: (not r["has_api"], r["fuente"]))
    for r in ordered:
        story.append(KeepTogether(_detail_block(r, st)))

    doc.build(story)
