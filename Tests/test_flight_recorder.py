"""
test_flight_recorder.py

Verifies the Flight Recorder's phase-detection state machine reaches all 11
phases, in order, on the canonical synthetic flight -- and that a flight
which never leaves the ground never falsely progresses.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Engine"))

from flight_recorder import FlightRecorder, FlightPhase  # noqa: E402
from synthetic_flight import generate_flight  # noqa: E402

EXPECTED_PHASE_ORDER = [
    "Flight Start", "Taxi", "Takeoff Roll", "Rotation", "Climb", "Cruise",
    "Descent", "Approach", "Landing", "Taxi In", "Shutdown",
]


class TestFlightRecorder(unittest.TestCase):
    def test_reaches_all_phases_in_order(self):
        recorder = FlightRecorder()
        for record in generate_flight(sample_interval=0.5, seed=42):
            recorder.update(record)

        phases_seen = [e["phase"] for e in recorder.phase_events]
        self.assertEqual(phases_seen, EXPECTED_PHASE_ORDER)
        self.assertEqual(recorder.phase, FlightPhase.SHUTDOWN)

    def test_consistent_across_sample_rates(self):
        for rate in (0.25, 0.5, 1.0):
            recorder = FlightRecorder()
            for record in generate_flight(sample_interval=rate, seed=42):
                recorder.update(record)
            phases_seen = [e["phase"] for e in recorder.phase_events]
            self.assertEqual(phases_seen, EXPECTED_PHASE_ORDER, f"mismatch at sample_interval={rate}")

    def test_idle_on_ground_never_progresses(self):
        """An aircraft sitting parked with the engine off should stay in
        Flight Start forever -- it should not spuriously detect a flight.
        """
        recorder = FlightRecorder()
        idle_record = {
            "time": "00:00:00", "elapsed_sec": 0.0, "altitude_ft": 650.0, "airspeed_kt": 0.0,
            "vertical_speed_fpm": 0.0, "heading_deg": 270.0, "pitch_deg": 0.0, "bank_deg": 0.0,
            "latitude_deg": 43.6, "longitude_deg": -79.6, "throttle_pct": 0.0, "flaps_pct": 0.0,
            "gear_down": True, "rpm": 0.0, "fuel_qty_gal": 40.0, "parking_brake": True,
            "engine_combustion": False, "autopilot_master": False, "sim_time_sec": 50000.0,
        }
        for i in range(50):
            record = dict(idle_record, elapsed_sec=i * 0.5)
            recorder.update(record)
        self.assertEqual(recorder.phase, FlightPhase.FLIGHT_START)
        self.assertEqual(len(recorder.phase_events), 1)

    def test_phase_slice_boundaries(self):
        """The Cruise slice should be overwhelmingly stable-vertical-speed
        samples. It isn't guaranteed to be 100% of them: phase transitions
        require a 3-second sustained condition (SUSTAIN_WINDOW_SEC) before
        confirming, specifically to reject single-sample noise -- which
        means a handful of already-descending samples can trail into the
        end of the Cruise slice while that confirmation window fills. That's
        the debounce working as designed, not a boundary bug.
        """
        recorder = FlightRecorder()
        for record in generate_flight(sample_interval=0.5, seed=42):
            recorder.update(record)

        cruise_slice = recorder.phase_slice(FlightPhase.CRUISE, FlightPhase.DESCENT)
        self.assertTrue(len(cruise_slice) > 0)
        stable_count = sum(1 for r in cruise_slice if abs(r["vertical_speed_fpm"]) < 400)
        self.assertGreater(stable_count / len(cruise_slice), 0.95)

        # The deliberate steep-bank excursion should be observable within this slice.
        self.assertGreater(max(abs(r["bank_deg"]) for r in cruise_slice), 30)


if __name__ == "__main__":
    unittest.main()
