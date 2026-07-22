"""
test_mistake_detector.py

Verifies the canonical mistake detector: it flags the deliberate
imperfections in the synthetic flight, every mistake carries a timestamp,
and -- the important regression case -- bounced-landing detection doesn't
false-positive on ordinary telemetry noise. That false positive was a real
bug found during development: recorder.altitude_agl_ft() uses the ground
reference *as it ended up after the whole flight was replayed*, not as it
was at the moment of touchdown, so a few feet of ordinary sensor jitter
during rollout looked like a bounce. Fixed by measuring against the
touchdown sample's own altitude instead, with a two-consecutive-samples
requirement. This test pins that fix down across many seeds/rates rather
than trusting it not to regress.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Engine"))

from flight_recorder import FlightRecorder  # noqa: E402
from synthetic_flight import generate_flight  # noqa: E402
import mistake_detector as md  # noqa: E402


def _replay(seed=42, sample_interval=0.5):
    recorder = FlightRecorder()
    for record in generate_flight(sample_interval=sample_interval, seed=seed):
        recorder.update(record)
    return recorder


class TestMistakeDetector(unittest.TestCase):
    def test_flags_known_bank_excursion_in_cruise(self):
        recorder = _replay()
        result = md.evaluate_cruise(recorder)
        categories = [m.category for m in result.mistakes]
        self.assertIn("excessive_bank", categories)

    def test_flags_known_approach_and_landing_issues(self):
        recorder = _replay()
        approach = md.evaluate_approach(recorder)
        landing_eval, landing_metrics = md.evaluate_landing(recorder)

        approach_categories = [m.category for m in approach.mistakes]
        landing_categories = [m.category for m in landing_eval.mistakes]

        self.assertIn("incorrect_speed", approach_categories)
        self.assertIn("excessive_descent_rate", approach_categories)
        self.assertIn("hard_landing", landing_categories)
        self.assertIsNotNone(landing_metrics)

    def test_all_mistakes_have_timestamps_and_recommendations(self):
        recorder = _replay()
        all_mistakes = []
        all_mistakes += md.evaluate_takeoff(recorder).mistakes
        all_mistakes += md.evaluate_climb(recorder).mistakes
        all_mistakes += md.evaluate_cruise(recorder).mistakes
        all_mistakes += md.evaluate_approach(recorder).mistakes
        landing_eval, _ = md.evaluate_landing(recorder)
        all_mistakes += landing_eval.mistakes

        self.assertGreater(len(all_mistakes), 0)
        for m in all_mistakes:
            self.assertIsInstance(m.elapsed_sec, (int, float))
            self.assertIn(m.severity, ("minor", "moderate", "major"))
            self.assertTrue(m.explanation)
            self.assertTrue(m.recommendation)

    def test_bounce_detection_has_no_false_positives(self):
        """Regression test: ordinary telemetry jitter during rollout must
        not be mistaken for a bounced landing, across many seeds and
        sample rates.
        """
        for seed in range(1, 15):
            for rate in (0.25, 0.5, 1.0):
                recorder = _replay(seed=seed, sample_interval=rate)
                landing_eval, _ = md.evaluate_landing(recorder)
                bounced = any(m.category == "bounced_landing" for m in landing_eval.mistakes)
                self.assertFalse(bounced, f"false bounce detected at seed={seed} rate={rate}")

    def test_bounce_detection_catches_a_real_bounce(self):
        records = list(generate_flight(sample_interval=0.5, seed=42))
        recorder = FlightRecorder()
        touchdown_seen = False
        for i, record in enumerate(records):
            recorder.update(record)
            if recorder.phase.value == "Landing" and not touchdown_seen:
                touchdown_seen = True
                for j in range(i + 1, min(i + 4, len(records))):
                    records[j] = dict(records[j])
                    records[j]["altitude_ft"] = records[i]["altitude_ft"] + 15

        recorder2 = FlightRecorder()
        for record in records:
            recorder2.update(record)
        landing_eval, _ = md.evaluate_landing(recorder2)
        bounced = any(m.category == "bounced_landing" for m in landing_eval.mistakes)
        self.assertTrue(bounced, "a genuine 15ft re-ascent after touchdown should be detected as a bounce")


if __name__ == "__main__":
    unittest.main()
