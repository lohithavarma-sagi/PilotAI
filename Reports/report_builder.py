"""
report_builder.py

Builds the full structured instructor report from a completed flight:
Flight Summary, Flight Timeline, Detected Mistakes, Strengths, Scores,
Recommendations, Instructor Summary, and a Final Grade.

This is deliberately a plain-dict builder with no rendering logic --
json_report.py saves this dict as-is, and pdf_report.py / text_report.py
both render the *same* dict two different ways. Building the data once and
rendering it twice (JSON/PDF/text) avoids two places that could disagree
about what the report says.
"""

import datetime as dt
import math
from typing import Any, Dict, List, Optional

from instructor_summary import generate_instructor_summary, grade_label, letter_grade


def _haversine_nm(lat1, lon1, lat2, lon2) -> float:
    R_nm = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R_nm * math.asin(min(1.0, math.sqrt(a)))


def _track_distance_nm(history: List[Dict[str, Any]]) -> float:
    total = 0.0
    for i in range(1, len(history)):
        a, b = history[i - 1], history[i]
        total += _haversine_nm(a["latitude_deg"], a["longitude_deg"], b["latitude_deg"], b["longitude_deg"])
    return total


def _downsample(values: List[float], max_points: int = 300) -> List[float]:
    if len(values) <= max_points:
        return values
    step = len(values) / max_points
    return [values[int(i * step)] for i in range(max_points)]


def build_flight_summary(history: List[Dict[str, Any]], phase_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not history:
        return {}
    duration_sec = history[-1]["elapsed_sec"] - history[0]["elapsed_sec"]
    return {
        "date": dt.date.today().isoformat(),
        "start_time": history[0]["time"],
        "end_time": history[-1]["time"],
        "duration_sec": round(duration_sec, 1),
        "duration_str": f"{int(duration_sec // 60)}m {int(duration_sec % 60)}s",
        "phases_reached": [e["phase"] for e in phase_events],
        "max_altitude_ft": round(max(r["altitude_ft"] for r in history), 0),
        "max_airspeed_kt": round(max(r["airspeed_kt"] for r in history), 1),
        "min_fuel_qty_gal": round(min(r["fuel_qty_gal"] for r in history), 1),
        "track_distance_nm": round(_track_distance_nm(history), 1),
        "sample_count": len(history),
    }


def build_timeline(phase_events: List[Dict[str, Any]], mistakes: List[Dict[str, Any]],
                    checklist_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    timeline = []
    for e in phase_events:
        timeline.append({"elapsed_sec": e["elapsed_sec"], "time": e["time"], "type": "phase",
                          "text": f"Phase: {e['phase']}"})
    for m in mistakes:
        timeline.append({"elapsed_sec": m["elapsed_sec"], "time": m["time"], "type": "mistake",
                          "text": f"[{m['severity']}] {m['phase']}: {m['explanation']}"})
    for item in checklist_items:
        if item["completed"] and item["completed_at_elapsed_sec"] is not None:
            tag = "checklist_late" if item["out_of_sequence"] else "checklist"
            timeline.append({"elapsed_sec": item["completed_at_elapsed_sec"], "time": item.get("completed_at_time") or "",
                              "type": tag,
                              "text": f"Checklist: {item['description']}" + (" (late)" if item["out_of_sequence"] else "")})
    timeline.sort(key=lambda t: t["elapsed_sec"])
    return timeline


def build_performance_series(history: List[Dict[str, Any]]) -> Dict[str, List[float]]:
    return {
        "elapsed_sec": _downsample([r["elapsed_sec"] for r in history]),
        "altitude_ft": _downsample([r["altitude_ft"] for r in history]),
        "airspeed_kt": _downsample([r["airspeed_kt"] for r in history]),
        "vertical_speed_fpm": _downsample([r["vertical_speed_fpm"] for r in history]),
    }


def build_report(history: List[Dict[str, Any]], phase_events: List[Dict[str, Any]],
                  score_report: Dict[str, Any], checklist_summary: Dict[str, Any],
                  aircraft: str = "Cessna 172", use_llm_summary: bool = False) -> Dict[str, Any]:
    categories = score_report["categories"]
    landing_metrics = score_report.get("landing_metrics")
    mistakes = score_report.get("mistakes", [])
    overall_score = score_report["overall_score"]

    strengths = []
    for cat in categories.values():
        strengths.extend(cat.get("strengths", []))

    severity_rank = {"major": 0, "moderate": 1, "minor": 2}
    suggestions = []
    for m in sorted(mistakes, key=lambda m: severity_rank.get(m["severity"], 3)):
        if m["recommendation"] and m["recommendation"] not in suggestions:
            suggestions.append(m["recommendation"])

    report = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "aircraft": aircraft,
        "flight_summary": build_flight_summary(history, phase_events),
        "timeline": build_timeline(phase_events, mistakes, checklist_summary.get("items", [])),
        "scores": {"overall_score": overall_score, "categories": categories},
        "mistakes": mistakes,
        "strengths": strengths,
        "checklist": checklist_summary,
        "landing_metrics": landing_metrics,
        "suggestions": suggestions,
        "final_grade": {"letter": letter_grade(overall_score), "label": grade_label(overall_score)},
        "performance_series": build_performance_series(history),
    }
    report["instructor_summary"] = generate_instructor_summary(report, use_llm=use_llm_summary)
    return report
