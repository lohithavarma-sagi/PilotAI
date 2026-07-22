"""
text_report.py

Plain-text rendering of the full structured report dict (see
report_builder.py) -- what gets printed to the console when a flight
finishes, and saved as a human-readable .txt alongside the JSON and PDF.
"""

from typing import Any, Dict


def render_text_report(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("PilotAI Flight Report")
    lines.append("")
    lines.append(f"Flight: {report['aircraft']}")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append("")

    summary = report.get("flight_summary", {})
    if summary:
        lines.append("Flight Information:")
        lines.append(f"  Date: {summary.get('date', '-')}")
        lines.append(f"  Duration: {summary.get('duration_str', '-')}")
        lines.append(f"  Track distance: {summary.get('track_distance_nm', '-')} nm")
        lines.append(f"  Max altitude: {summary.get('max_altitude_ft', '-')} ft")
        lines.append(f"  Max airspeed: {summary.get('max_airspeed_kt', '-')} kt")
        lines.append(f"  Phases reached: {', '.join(summary.get('phases_reached', []))}")
        lines.append("")

    scores = report.get("scores", {})
    lines.append(f"Overall Score: {scores.get('overall_score', '-')}/100")
    for cat in scores.get("categories", {}).values():
        lines.append(f"  {cat['name']}: {cat['score']}/100")
    lines.append("")

    checklist = report.get("checklist", {})
    if checklist:
        lines.append(f"Checklist: {checklist.get('completed_count', 0)}/{checklist.get('total_count', 0)} completed")
        if checklist.get("missed"):
            lines.append(f"  Missed: {', '.join(checklist['missed'])}")
        if checklist.get("out_of_sequence"):
            lines.append(f"  Out of sequence: {', '.join(checklist['out_of_sequence'])}")
        lines.append("")

    timeline = report.get("timeline", [])
    if timeline:
        lines.append("Flight Timeline:")
        for t in timeline:
            time_label = t["time"] or f"{t['elapsed_sec']:.0f}s"
            lines.append(f"  [{time_label}] {t['text']}")
        lines.append("")

    mistakes = report.get("mistakes", [])
    lines.append("Detected Mistakes:")
    if mistakes:
        for m in mistakes:
            time_label = m["time"] or f"{m['elapsed_sec']:.0f}s"
            lines.append(f"  ⚠ [{time_label}] [{m['severity']}] {m['phase']}: {m['explanation']}")
    else:
        lines.append("  (none -- clean flight)")
    lines.append("")

    suggestions = report.get("suggestions", [])
    lines.append("Recommendations:")
    if suggestions:
        for s in suggestions:
            lines.append(f"  {s}")
    else:
        lines.append("  Keep flying like that.")
    lines.append("")

    strengths = report.get("strengths", [])
    if strengths:
        lines.append("Strengths:")
        for s in strengths:
            lines.append(f"  ✓ {s}")
        lines.append("")

    instructor_summary = report.get("instructor_summary")
    if instructor_summary:
        lines.append("Instructor Summary:")
        lines.append(instructor_summary)
        lines.append("")

    final_grade = report.get("final_grade")
    if final_grade:
        lines.append(f"Final Grade: {final_grade['letter']} ({final_grade['label']})")

    return "\n".join(lines)
