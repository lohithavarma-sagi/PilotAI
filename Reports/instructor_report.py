"""
instructor_report.py

The Flight Report Generator. Builds the full structured report once
(report_builder.build_report) and renders it three ways -- JSON, PDF, and
plain text -- so nothing about what the report says can drift between
formats. This is the function run_pilotai.py calls once a flight has been
analyzed (see Engine/analyze.py).
"""

import logging
import os
from typing import Any, Dict

from report_builder import build_report
from json_report import save_json_report
from pdf_report import build_pdf
from text_report import render_text_report

logger = logging.getLogger("pilotai.reports")


def generate_full_report(recorder, score_report: Dict[str, Any], checklist_summary: Dict[str, Any],
                          flight_json_path: str, use_llm_summary: bool = False) -> Dict[str, str]:
    """Builds and saves the JSON, PDF, and text report for a completed flight.
    Returns the paths written.
    """
    report = build_report(recorder.history, recorder.phase_events, score_report, checklist_summary,
                           use_llm_summary=use_llm_summary)

    json_path = save_json_report(report, flight_json_path)

    text = render_text_report(report)
    base, _ext = os.path.splitext(flight_json_path)
    text_path = f"{base}_report.txt"
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")

    pdf_path = f"{base}_report.pdf"
    try:
        build_pdf(report, pdf_path)
    except Exception:
        logger.exception("PDF report generation failed -- JSON and text reports were still saved.")
        pdf_path = None

    logger.info(f"Report generated: {json_path}" + (f", {pdf_path}" if pdf_path else "") + f", {text_path}")
    print(text)

    paths = {"json": json_path, "text": text_path}
    if pdf_path:
        paths["pdf"] = pdf_path
    return paths
