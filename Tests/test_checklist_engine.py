"""
test_checklist_engine.py

Verifies the Checklist System: completes correctly on a clean flight,
correctly detects an item that's never satisfied (missed), and correctly
detects an item satisfied later than expected (out of sequence). These
three scenarios were found by hand during development (see git history /
conversation) -- including a real bug where several items could trivially
"complete" at elapsed_sec 0 because the aircraft's pre-flight default state
happened to satisfy their condition. These tests pin that fix down.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Engine"))

from flight_recorder import FlightRecorder, FlightPhase  # noqa: E402
from synthetic_flight import generate_flight  # noqa: E402
from checklist_engine import ChecklistEngine  # noqa: E402


def _run_checklist(mutate=None, seed=42):
    recorder = FlightRecorder()
    checklist = ChecklistEngine()
    for record in generate_flight(sample_interval=0.5, seed=seed):
        if mutate:
            mutate(record, recorder.phase)
        recorder.update(record)
        checklist.update(record, recorder.phase)
    checklist.finalize()
    return checklist.summary()


class TestChecklistEngine(unittest.TestCase):
    def test_clean_flight_completes_everything(self):
        summary = _run_checklist()
        self.assertEqual(summary["completed_count"], summary["total_count"])
        self.assertEqual(summary["missed"], [])
        self.assertEqual(summary["out_of_sequence"], [])

    def test_no_item_completes_before_its_gate_phase(self):
        """Regression test for the elapsed_sec==0 trivial-completion bug:
        every checklist item with a not_before gate must not be marked
        completed at a sample belonging to an earlier phase than its gate.
        """
        recorder = FlightRecorder()
        checklist = ChecklistEngine()
        phase_at_completion = {}
        for record in generate_flight(sample_interval=0.5, seed=42):
            recorder.update(record)
            checklist.update(record, recorder.phase)
            for item in checklist.newly_completed:
                phase_at_completion[item.item_id] = recorder.phase
        checklist.finalize()

        phase_order = {p: i for i, p in enumerate(FlightPhase)}
        for item in checklist.items:
            if item.not_before is not None and item.item_id in phase_at_completion:
                completed_phase = phase_at_completion[item.item_id]
                self.assertGreaterEqual(
                    phase_order[completed_phase], phase_order[item.not_before],
                    f"{item.item_id} completed in {completed_phase} before its gate {item.not_before}",
                )

    def test_never_satisfied_item_is_missed(self):
        def mutate(record, phase):
            record["flaps_pct"] = max(record["flaps_pct"], 10.0)  # never fully retract
            if record["autopilot_master"] is False:
                record["autopilot_master"] = True  # never disengage

        summary = _run_checklist(mutate=mutate)
        self.assertIn("Takeoff flaps retracted", summary["missed"])
        self.assertIn("Autopilot disengaged for landing", summary["missed"])

    def test_late_completion_is_out_of_sequence(self):
        def mutate(record, phase):
            if phase in (FlightPhase.CLIMB, FlightPhase.CRUISE):
                record["flaps_pct"] = max(record["flaps_pct"], 5.0)

        summary = _run_checklist(mutate=mutate)
        self.assertEqual(summary["missed"], [])
        self.assertIn("Takeoff flaps retracted", summary["out_of_sequence"])


if __name__ == "__main__":
    unittest.main()
