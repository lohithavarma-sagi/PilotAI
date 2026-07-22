"""
analyze.py

The batch analysis pipeline: given a complete recorded flight (a file
written by the C# Connector, or a synthetic one from synthetic_flight.py),
replay it through the Flight Recorder and Checklist Engine, then score it.

There is no live/streaming path anymore -- see docs/ARCHITECTURE.md for why
PilotAI moved to a fully local, record-then-analyze workflow instead of a
live dashboard. That means this file is deliberately simple: no threads, no
locks, no per-sample callbacks, just "replay everything, then score it."
"""

import csv
import json
from typing import Any, Dict, List, Tuple

from checklist_engine import ChecklistEngine
from flight_recorder import FlightRecorder
from scoring_engine import score_flight
from telemetry_schema import coerce_record


def load_flight_records(path: str) -> List[Dict[str, Any]]:
    """Load a flight file, JSON or CSV. Supports both the wrapped shape
    FlightRecorder.save() writes ({"records": [...], "phase_events": [...]})
    and a bare JSON array, since the C# Connector and synthetic_flight.py
    both just write a plain list.
    """
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        records = data["records"] if isinstance(data, dict) and "records" in data else data
        return [coerce_record(r) for r in records]

    records = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(coerce_record(dict(row)))
    return records


def analyze_records(records: List[Dict[str, Any]]) -> Tuple[FlightRecorder, Dict[str, Any], Dict[str, Any]]:
    """Replay a list of telemetry records through the Flight Recorder and
    Checklist Engine, then score the result. Returns (recorder, score_report,
    checklist_summary).
    """
    if len(records) < 10:
        raise ValueError("Flight file is too short to analyze (need at least 10 samples).")

    recorder = FlightRecorder()
    checklist = ChecklistEngine()
    for record in records:
        recorder.update(record)
        checklist.update(record, recorder.phase)
    checklist.finalize()

    checklist_summary = checklist.summary()
    score_report = score_flight(recorder, checklist_summary)
    return recorder, score_report, checklist_summary


def analyze_flight_file(path: str) -> Tuple[FlightRecorder, Dict[str, Any], Dict[str, Any]]:
    records = load_flight_records(path)
    return analyze_records(records)
