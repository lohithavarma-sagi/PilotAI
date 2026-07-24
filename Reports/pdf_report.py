"""
pdf_report.py

Renders the same report dict that json_report.py saves and text_report.py
prints as text, but as a concise, printable PDF (target: 1-3 pages) --
title page, executive summary, category scores, key mistakes, strengths,
areas for improvement, and a short instructor summary -- with "Generated
automatically by PilotAI" on every page footer. Meant to be professional
enough to hand directly to a student after a lesson, and short enough that
an instructor actually reads the whole thing.

The full-detail data (every mistake, the complete timeline, the raw
performance series) still lives in the JSON and text reports -- this file
only trims what it *renders*, not the underlying report_builder.py data.

Uses reportlab (already the project's one third-party dependency).
"""

import os
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

STYLES = getSampleStyleSheet()
H1 = STYLES["Heading1"]
H2 = STYLES["Heading2"]
BODY = STYLES["BodyText"]
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=9.5, leading=13)
TITLE = ParagraphStyle("TitlePage", parent=STYLES["Title"], fontSize=24, spaceAfter=10, alignment=TA_CENTER)
TITLE_SUB = ParagraphStyle("TitleSub", parent=BODY, fontSize=12, alignment=TA_CENTER, textColor=colors.HexColor("#667085"))
GRADE_STYLE = ParagraphStyle("Grade", parent=STYLES["Title"], fontSize=44, leading=52, alignment=TA_CENTER, spaceAfter=6)
GRADE_LABEL_STYLE = ParagraphStyle("GradeLabel", parent=BODY, fontSize=13, leading=16, alignment=TA_CENTER, spaceAfter=2)

FOOTER_TEXT = "Generated automatically by PilotAI"

KEY_MISTAKES_LIMIT = 6
STRENGTHS_LIMIT = 5
IMPROVEMENT_LIMIT = 5
SEVERITY_RANK = {"major": 0, "moderate": 1, "minor": 2}


def _grade_color_hex(score: int) -> str:
    if score >= 90:
        return "#0f766e"
    if score >= 70:
        return "#b45309"
    return "#b42318"


def _draw_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#667085"))
    canvas.drawCentredString(doc.pagesize[0] / 2, 0.4 * inch, FOOTER_TEXT)
    canvas.drawRightString(doc.pagesize[0] - 0.6 * inch, 0.4 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _title_page(report: Dict[str, Any]) -> list:
    summary = report.get("flight_summary", {})
    story = [
        Spacer(1, 1.0 * inch),
        Paragraph("PilotAI Flight Evaluation Report", TITLE),
        Spacer(1, 0.4 * inch),
    ]
    rows = [
        ["Student Pilot", report.get("student_name", "Student Pilot")],
        ["Instructor / Supervisor", report.get("instructor_name", "Instructor")],
        ["Date", summary.get("date", "-")],
        ["Time", summary.get("start_time", "-")],
        ["Aircraft", report.get("aircraft", "-")],
        ["Flight Duration", summary.get("duration_str", "-")],
    ]
    table = Table(rows, colWidths=[180, 220])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#667085")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(table)
    story.append(PageBreak())
    return story


def _executive_summary(report: Dict[str, Any]) -> list:
    scores = report.get("scores", {})
    overall = scores.get("overall_score", 0)
    final_grade = report.get("final_grade", {})
    story = [Paragraph("Executive Summary", H1)]

    story.append(Paragraph(f"<font color='{_grade_color_hex(overall)}'>{overall}/100</font>", GRADE_STYLE))
    if final_grade:
        story.append(Paragraph(
            f"Grade {final_grade.get('letter', '-')} &nbsp;&mdash;&nbsp; {final_grade.get('label', '-')}",
            GRADE_LABEL_STYLE,
        ))
    story.append(Spacer(1, 10))

    instructor_summary = report.get("instructor_summary") or ""
    overview = " ".join(instructor_summary.split("\n\n")[:1]).strip()
    if overview:
        story.append(Paragraph(overview, BODY))
    story.append(Spacer(1, 14))
    return story


def _category_scores_table(report: Dict[str, Any]) -> list:
    scores = report.get("scores", {})
    categories = scores.get("categories", {})
    story = [Paragraph("Category Scores", H2)]
    rows = [["Category", "Score"]]
    for cat in categories.values():
        rows.append([cat["name"], f"{cat['score']}/100"])
    table = Table(rows, colWidths=[300, 100])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    story.append(Spacer(1, 14))
    return story


def _key_mistakes(report: Dict[str, Any]) -> list:
    mistakes: List[Dict[str, Any]] = report.get("mistakes", [])
    story = [Paragraph("Key Mistakes", H2)]
    if not mistakes:
        story.append(Paragraph("No significant mistakes detected -- a clean flight.", SMALL))
        story.append(Spacer(1, 14))
        return story

    ranked = sorted(mistakes, key=lambda m: (SEVERITY_RANK.get(m["severity"], 3), m["elapsed_sec"]))
    top = ranked[:KEY_MISTAKES_LIMIT]
    for m in top:
        time_label = m["time"] or f"{m['elapsed_sec']:.0f}s"
        issue = m["category"].replace("_", " ").title()
        story.append(Paragraph(
            f"<b>[{time_label}] {issue}</b> ({m['severity']}) &mdash; {m['phase']}", SMALL
        ))
        story.append(Paragraph(m["explanation"], SMALL))
        if m.get("recommendation"):
            story.append(Paragraph(f"<i>Recommendation:</i> {m['recommendation']}", SMALL))
        story.append(Spacer(1, 6))
    remaining = len(mistakes) - len(top)
    if remaining > 0:
        story.append(Paragraph(
            f"+ {remaining} additional lower-severity item(s) -- see the full JSON/text report.", SMALL
        ))
    story.append(Spacer(1, 10))
    return story


def _bulleted(items: List[str], style=SMALL) -> list:
    return [Paragraph(f"&#8226; {text}", style) for text in items]


def _strengths(report: Dict[str, Any]) -> list:
    strengths = report.get("strengths", [])[:STRENGTHS_LIMIT]
    story = [Paragraph("Strengths", H2)]
    if strengths:
        story.extend(_bulleted(strengths))
    else:
        story.append(Paragraph("No specific strengths stood out as exceptional this flight.", SMALL))
    story.append(Spacer(1, 14))
    return story


def _areas_for_improvement(report: Dict[str, Any]) -> list:
    suggestions = report.get("suggestions", [])[:IMPROVEMENT_LIMIT]
    story = [Paragraph("Areas for Improvement", H2)]
    if suggestions:
        story.extend(_bulleted(suggestions))
    else:
        story.append(Paragraph("Keep flying like that.", SMALL))
    story.append(Spacer(1, 14))
    return story


def _instructor_summary_paragraph(report: Dict[str, Any]) -> list:
    instructor_summary = report.get("instructor_summary") or ""
    if not instructor_summary:
        return []
    condensed = " ".join(instructor_summary.split("\n\n"))
    return [Paragraph("Instructor Summary", H2), Paragraph(condensed, BODY)]


def build_pdf(report: Dict[str, Any], out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    doc = SimpleDocTemplate(out_path, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.7 * inch)
    story = []

    story.extend(_title_page(report))
    story.extend(_executive_summary(report))
    story.extend(_category_scores_table(report))
    story.extend(_key_mistakes(report))
    story.extend(_strengths(report))
    story.extend(_areas_for_improvement(report))
    story.extend(_instructor_summary_paragraph(report))

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return out_path
