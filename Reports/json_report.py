"""
json_report.py

Saves a report dict (from report_builder.build_report) as JSON, next to
the flight recording it was generated from.
"""

import json
import os


def save_json_report(report: dict, flight_json_path: str) -> str:
    base, _ext = os.path.splitext(flight_json_path)
    out_path = f"{base}_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return out_path
