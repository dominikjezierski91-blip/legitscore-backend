"""
Generowanie PDF raportu — stały layout, deterministyczny, bez LLM.
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Preformatted


DISCLAIMER = (
    "Raport ma charakter analityczny i pomocniczy. "
    "Nie stanowi certyfikatu ani 100% gwarancji."
)


def _footer_canvas(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawString(15 * mm, 12 * mm, DISCLAIMER)
    canvas.restoreState()


def generate_report_pdf(case_id: str, report_text: str, output_path: str) -> None:
    """
    Generuje PDF z raportem: nagłówek, meta (case_id), blok tekstu raportu,
    stopka z disclaimer. Stały layout, 1–2 strony max.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
    )
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=9,
        leading=11,
    )

    story = []
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=14,
        spaceAfter=6,
    )
    story.append(Paragraph("LegitScore — Raport analityczny", title_style))
    story.append(Paragraph(f"Case ID: {case_id}", styles["Normal"]))
    story.append(Spacer(1, 6 * mm))
    story.append(Preformatted(report_text, body_style))

    doc.build(story, onFirstPage=_footer_canvas, onLaterPages=_footer_canvas)
