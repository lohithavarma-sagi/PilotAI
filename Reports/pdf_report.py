"""
pdf_report.py

Renders the same report dict that json_report.py saves and text_report.py
prints as text, but as a formatted, printable PDF -- a title page, flight
information, scores, a performance graph, the flight timeline, detected
mistakes, recommendations, strengths, the instructor summary, and a final
grade, with "Generated automatically by PilotAI" on every page footer.
Meant to be professional enough to hand directly to a student after a
lesson.

Uses reportlab's own charting (reportlab.graphics.charts.lineplots), not
matplotlib -- this project already depends on reportlab for PDF generation,
so drawing the graph with the same library avoids adding a second charting
dependency just for one graph.
"""

import os
from typing import Any, Dict

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.lineplots import LinePlot

STYLES = getSampleStyleSheet()
H1 = STYLES["Heading1"]
H2 = STYLES["Heading2"]
BODY = STYLES["BodyText"]
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=9, leading=12)
TITLE = ParagraphStyle("TitlePage", parent=STYLES["Title"], fontSize=28, spaceAfter=18, alignment=TA_CENTER)
TITLE_SUB = ParagraphStyle("TitleSub", parent=BODY, fontSize=13, alignment=TA_CENTER, textColor=colors.HexColor("#667085"))
GRADE_STYLE = ParagraphStyle("Grade", parent=STYLES["Title"], fontSize=48, alignment=TA_CENTER, spaceAfter=6)

FOOTER_TEXT = "Generated automatically by PilotAI"


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


def _build_performance_chart(series: Dict[str, list]) -> Drawing:
    drawing = Drawing(460, 200)
    times = series.get("elapsed_sec", [])
    if not times:
        return drawing

    altitude = series["altitude_ft"]
    airspeed = series["airspeed_kt"]

    # Two series on one plot, with altitude scaled down so it shares a
    # sensible axis range with airspeed (feet vs. knots differ by ~30x) --
    # a simple, honest way to show both trends on one small chart without
    # pulling in a second-axis-capable charting library.
    max_alt = max(altitude) or 1
    scaled_altitude = [a / max_alt * 150 for a in altitude]

    plot = LinePlot()
    plot.x = 50
    plot.y = 30
    plot.height = 140
    plot.width = 380
    plot.data = [list(zip(times, scaled_altitude)), list(zip(times, airspeed))]
    plot.lines[0].strokeColor = colors.HexColor("#2f67c7")
    plot.lines[1].strokeColor = colors.HexColor("#b45309")
    plot.lines[0].strokeWidth = 1.2
    plot.lines[1].strokeWidth = 1.2
    plot.xValueAxis.valueMin = min(times)
    plot.xValueAxis.valueMax = max(times)
    plot.yValueAxis.valueMin = 0

    drawing.add(plot)
    drawing.add(String(50, 185, "Altitude (scaled) - blue   |   Airspeed (kt) - orange", fontSize=8))
    return drawing


def _title_page(report: Dict[str, Any]) -> list:
    summary = report.get("flight_summary", {})
    story = [
        Spacer(1, 1.8 * inch),
        Paragraph("PilotAI Flight Report", TITLE),
        Paragraph("Instructor Evaluation", TITLE_SUB),
        Spacer(1, 0.6 * inch),
    ]
    rows = [
        ["Aircraft", report.get("aircraft", "-")],
        ["Date", summary.get("date", "-")],
        ["Duration", summary.get("duration_str", "-")],
    ]
    table = Table(rows, colWidths=[150, 250])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#667085")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.5 * inch))
    overall = report.get("scores", {}).get("overall_score")
    if overall is not None:
        story.append(Paragraph(
            f"<font color='{_grade_color_hex(overall)}'>{overall}/100</font>", GRADE_STYLE
        ))
    story.append(PageBreak())
    return story


def _bulleted(items, style=SMALL) -> list:
    return [Paragraph(f"&#8226; {text}", style) for text in items]


def build_pdf(report: Dict[str, Any], out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    doc = SimpleDocTemplate(out_path, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.7 * inch)
    story = []

    story.extend(_title_page(report))

    summary = report.get("flight_summary", {})
    story.append(Paragraph("Flight Information", H2))
    rows = [
        ["Aircraft", report.get("aircraft", "-")],
        ["Date", summary.get("date", "-")],
        ["Duration", summary.get("duration_str", "-")],
        ["Track distance", f"{summary.get('track_distance_nm', '-')} nm"],
        ["Max altitude", f"{summary.get('max_altitude_ft', '-')} ft"],
        ["Max airspeed", f"{summary.get('max_airspeed_kt', '-')} kt"],
        ["Phases reached", Paragraph(", ".join(summary.get("phases_reached", [])), SMALL)],
    ]
    table = Table(rows, colWidths=[130, 320])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#667085")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    story.append(Spacer(1, 14))

    scores = report.get("scores", {})
    overall = scores.get("overall_score")
    if overall is not None:
        story.append(Paragraph(f"Overall Score: <font color='{_grade_color_hex(overall)}'>{overall}/100</font>", H2))
        cat_rows = [["Category", "Score"]]
        for cat in scores.get("categories", {}).values():
            cat_rows.append([cat["name"], f"{cat['score']}/100"])
        cat_table = Table(cat_rows, colWidths=[250, 100])
        cat_table.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(cat_table)
        story.append(Spacer(1, 14))

    series = report.get("performance_series")
    if series and series.get("elapsed_sec"):
        story.append(Paragraph("Performance", H2))
        story.append(_build_performance_chart(series))
        story.append(Spacer(1, 14))

    timeline = report.get("timeline", [])
    if timeline:
        story.append(Paragraph("Flight Timeline", H2))
        for t in timeline:
            time_label = t["time"] or f"{t['elapsed_sec']:.0f}s"
            story.append(Paragraph(f"&#8226; [{time_label}] {t['text']}", SMALL))
        story.append(Spacer(1, 14))

    mistakes = report.get("mistakes", [])
    story.append(Paragraph("Detected Mistakes", H2))
    if mistakes:
        for m in mistakes:
            time_label = m["time"] or f"{m['elapsed_sec']:.0f}s"
            story.append(Paragraph(
                f"&#8226; [{time_label}] [{m['severity']}] {m['phase']}: {m['explanation']}", SMALL
            ))
    else:
        story.append(Paragraph("No mistakes detected -- a clean flight.", SMALL))
    story.append(Spacer(1, 14))

    suggestions = report.get("suggestions", [])
    story.append(Paragraph("Recommendations", H2))
    if suggestions:
        story.extend(_bulleted(suggestions))
    else:
        story.append(Paragraph("Keep flying like that.", SMALL))
    story.append(Spacer(1, 14))

    strengths = report.get("strengths", [])
    if strengths:
        story.append(Paragraph("Strengths", H2))
        story.extend(_bulleted(strengths))
        story.append(Spacer(1, 14))

    instructor_summary = report.get("instructor_summary")
    if instructor_summary:
        story.append(Paragraph("Instructor Summary", H2))
        for paragraph in instructor_summary.split("\n\n"):
            story.append(Paragraph(paragraph, BODY))
            story.append(Spacer(1, 6))
        story.append(Spacer(1, 8))

    final_grade = report.get("final_grade")
    if final_grade:
        story.append(Paragraph("Final Grade", H2))
        story.append(Paragraph(
            f"<font size=22 color='{_grade_color_hex(overall or 0)}'>{final_grade['letter']}</font> "
            f"&nbsp;&nbsp;{final_grade['label']}",
            BODY,
        ))

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return out_path
