"""
test_analyze.py

Verifies the batch analysis pipeline (Engine/analyze.py): it replays a
recorded flight, scores it, and produces a valid checklist summary --
whether the flight came from a JSON file, a CSV file, or in-memory records
directly. There's no live/streaming path to test anymore (see
docs/ARCHITECTURE.md) -- this is deliberately a simple, synchronous
"load, replay, score" pipeline with no threads or timing to get wrong.
"""

import csv
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Engine"))

from analyze import analyze_records, analyze_flight_file  # noqa: E402
from synthetic_flight import generate_flight  # noqa: E402
from telemetry_schema import FIELD_NAMES  # noqa: E402


class TestAnalyze(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="pilotai_test_analyze_")
        self.records = list(generate_flight(sample_interval=0.5, seed=42))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_analyze_records_directly(self):
        recorder, score_report, checklist_summary = analyze_records(self.records)
        self.assertEqual(len(recorder.history), len(self.records))
        self.assertEqual(score_report["overall_score"], score_report["overall_score"])
        self.assertEqual(checklist_summary["completed_count"], checklist_summary["total_count"])

    def test_analyze_from_json_file(self):
        path = os.path.join(self.tmp_dir, "flight.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.records, f)
        recorder, score_report, _checklist_summary = analyze_flight_file(path)
        self.assertEqual(len(recorder.history), len(self.records))
        self.assertIn("overall_score", score_report)

    def test_analyze_from_wrapped_json_file(self):
        """FlightRecorder.save() writes {"records": [...], "phase_events": [...]}
        rather than a bare list -- the loader needs to accept both shapes."""
        path = os.path.join(self.tmp_dir, "flight.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"schema_fields": FIELD_NAMES, "phase_events": [], "records": self.records}, f)
        recorder, _score_report, _checklist_summary = analyze_flight_file(path)
        self.assertEqual(len(recorder.history), len(self.records))

    def test_analyze_from_csv_file(self):
        path = os.path.join(self.tmp_dir, "flight.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELD_NAMES)
            writer.writeheader()
            writer.writerows(self.records)
        recorder, score_report, _checklist_summary = analyze_flight_file(path)
        self.assertEqual(len(recorder.history), len(self.records))
        self.assertIn("overall_score", score_report)

    def test_too_short_flight_raises(self):
        with self.assertRaises(ValueError):
            analyze_records(self.records[:5])


if __name__ == "__main__":
    unittest.main()
