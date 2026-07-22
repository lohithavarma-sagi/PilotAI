"""
test_scoring_engine.py

Verifies the AI Flight Analyzer's scoring: that it flags the deliberate
imperfections baked into the synthetic flight (fast/steep/hard landing,
one steep-bank excursion) and that every mistake with points deducted
carries both an explanation and a recommendation.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Engine"))

from flight_recorder import FlightRecorder  # noqa: E402
from synthetic_flight import generate_flight  # noqa: E402
from scoring_engine import score_flight  # noqa: E402


def _scored_synthetic_flight(seed=42):
    recorder = FlightRecorder()
    for record in generate_flight(sample_interval=0.5, seed=seed):
        recorder.update(record)
    return score_flight(recorder)


class TestScoringEngine(unittest.TestCase):
    def test_all_seven_categories_present(self):
        report = _scored_synthetic_flight()
        expected = {"Takeoff", "Climb", "Cruise", "Approach", "Landing", "Aircraft Control", "Checklist Discipline"}
        self.assertEqual(set(report["categories"].keys()), expected)
        self.assertIn("overall_score", report)

    def test_flags_known_landing_issues(self):
        report = _scored_synthetic_flight()
        landing = report["categories"]["Landing"]
        approach = report["categories"]["Approach"]
        landing_explanations = " ".join(m["explanation"] for m in landing["mistakes"])
        approach_explanations = " ".join(m["explanation"] for m in approach["mistakes"])
        self.assertIn("Descent rate on final", approach_explanations)
        self.assertIn("Hard touchdown", landing_explanations)
        self.assertLess(landing["score"], 100)
        self.assertLess(approach["score"], 100)

    def test_flags_known_bank_excursion(self):
        report = _scored_synthetic_flight()
        control = report["categories"]["Aircraft Control"]
        explanations = " ".join(m["explanation"] for m in control["mistakes"])
        self.assertIn("bank angle", explanations.lower())

    def test_every_mistake_has_explanation_and_recommendation(self):
        report = _scored_synthetic_flight()
        for cat in report["categories"].values():
            for m in cat["mistakes"]:
                self.assertTrue(m["explanation"])
                self.assertTrue(m["recommendation"])

    def test_mistakes_carry_timestamps(self):
        """Every mistake needs a timestamp per spec -- not just a category and reason."""
        report = _scored_synthetic_flight()
        for m in report["mistakes"]:
            self.assertIsInstance(m["elapsed_sec"], (int, float))
            self.assertIn(m["severity"], ("minor", "moderate", "major"))

    def test_score_consistent_across_sample_rates(self):
        scores = set()
        for rate in (0.25, 0.5, 1.0):
            recorder = FlightRecorder()
            for record in generate_flight(sample_interval=rate, seed=42):
                recorder.update(record)
            scores.add(score_flight(recorder)["overall_score"])
        self.assertEqual(len(scores), 1, f"overall_score varied by sample rate: {scores}")

    def test_checklist_summary_feeds_checklist_discipline_category(self):
        recorder = FlightRecorder()
        for record in generate_flight(sample_interval=0.5, seed=42):
            recorder.update(record)
        checklist_summary = {"missed": ["Some item"], "out_of_sequence": []}
        report = score_flight(recorder, checklist_summary)
        checklist_cat = report["categories"]["Checklist Discipline"]
        self.assertLess(checklist_cat["score"], 100)
        self.assertIn("Some item", checklist_cat["mistakes"][0]["explanation"])


if __name__ == "__main__":
    unittest.main()
