"""
test_reports.py

Verifies the Flight Report Generator produces valid JSON, PDF, and text
output from a completed flight, and that the numbers agree across all
three (they're rendered from the same report dict, but this pins that
down rather than assuming it).
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "Engine"))
sys.path.insert(0, os.path.join(REPO_ROOT, "Reports"))

from analyze import analyze_records  # noqa: E402
from synthetic_flight import generate_flight  # noqa: E402
from instructor_report import generate_full_report  # noqa: E402


class TestReports(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="pilotai_test_reports_")
        records = list(generate_flight(sample_interval=0.5, seed=42))
        self.recorder, self.score_report, self.checklist_summary = analyze_records(records)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_generates_json_pdf_and_text(self):
        flight_path = self.recorder.save(self.tmp_dir)
        paths = generate_full_report(self.recorder, self.score_report, self.checklist_summary, flight_path)

        self.assertTrue(os.path.exists(paths["json"]))
        self.assertTrue(os.path.exists(paths["text"]))
        self.assertIn("pdf", paths)
        self.assertTrue(os.path.exists(paths["pdf"]))
        self.assertGreater(os.path.getsize(paths["pdf"]), 1000)

    def test_json_report_score_matches_scoring_engine(self):
        flight_path = self.recorder.save(self.tmp_dir)
        paths = generate_full_report(self.recorder, self.score_report, self.checklist_summary, flight_path)
        with open(paths["json"], "r", encoding="utf-8") as f:
            report = json.load(f)
        self.assertEqual(report["scores"]["overall_score"], self.score_report["overall_score"])

    def test_text_report_mentions_known_landing_issue(self):
        flight_path = self.recorder.save(self.tmp_dir)
        paths = generate_full_report(self.recorder, self.score_report, self.checklist_summary, flight_path)
        with open(paths["text"], "r", encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Hard touchdown", text)

    def test_report_includes_instructor_summary_and_final_grade(self):
        flight_path = self.recorder.save(self.tmp_dir)
        paths = generate_full_report(self.recorder, self.score_report, self.checklist_summary, flight_path)
        with open(paths["json"], "r", encoding="utf-8") as f:
            report = json.load(f)
        self.assertTrue(report["instructor_summary"])
        self.assertIn(report["final_grade"]["letter"], ("A", "B", "C", "D", "F"))

    def test_no_networking_or_voice_modules_remain(self):
        """This is now a fully local, batch-only pipeline -- these files
        should not exist anymore (regression test for the local-first
        refactor, not just a design intention)."""
        removed = [
            os.path.join(REPO_ROOT, "Dashboard"),
            os.path.join(REPO_ROOT, "Engine", "coach.py"),
            os.path.join(REPO_ROOT, "Engine", "voice.py"),
            os.path.join(REPO_ROOT, "Engine", "telemetry_source.py"),
            os.path.join(REPO_ROOT, "Connector", "TelemetryStreamer.cs"),
        ]
        for path in removed:
            self.assertFalse(os.path.exists(path), f"{path} should have been removed")


if __name__ == "__main__":
    unittest.main()
