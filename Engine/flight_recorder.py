"""
flight_recorder.py

The Flight Recorder is the single source of truth for "what phase of flight
is this, right now" -- both while a flight is in progress (so the Live Coach
and Checklist Engine know what rules apply) and afterward (the post-flight
Analyzer replays a saved flight through this same state machine instead of
re-implementing phase detection a second time; keeping one implementation
avoids the live and post-flight views of a flight ever disagreeing about
where takeoff ended and cruise began).

Scope note (v1): this models a single continuous flight, start to shutdown,
moving forward through phases in order. It does not yet support touch-and-goes
or multiple landings in one session -- seeing the aircraft climb again after
a landing restarts a new FlightRecorder rather than looping the same one.
That's a deliberate v1 boundary, not an oversight; see docs/ROADMAP.md.
"""

import datetime as dt
import json
import os
from collections import deque
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from telemetry_schema import FIELD_NAMES


class FlightPhase(str, Enum):
    FLIGHT_START = "Flight Start"
    TAXI = "Taxi"
    TAKEOFF_ROLL = "Takeoff Roll"
    ROTATION = "Rotation"
    CLIMB = "Climb"
    CRUISE = "Cruise"
    DESCENT = "Descent"
    APPROACH = "Approach"
    LANDING = "Landing"
    TAXI_IN = "Taxi In"
    SHUTDOWN = "Shutdown"


# Order defines the only forward transitions this v1 state machine allows.
PHASE_ORDER = list(FlightPhase)

# --- Thresholds (generic Cessna 172 numbers; see README's "known limitations") ---
TAXI_MIN_KT = 2.0
ROTATION_SPEED_KT = 50.0
TAKEOFF_THROTTLE_PCT = 85.0
CLIMB_VS_THRESHOLD_FPM = 200.0
CRUISE_VS_STABLE_FPM = 150.0
DESCENT_VS_THRESHOLD_FPM = -200.0
APPROACH_AGL_FT = 1500.0
GROUND_AGL_MARGIN_FT = 20.0
TAXI_IN_MAX_KT = 35.0
SUSTAIN_WINDOW_SEC = 3.0  # how long a condition must hold before we trust it, to reject single-sample noise


class FlightRecorder:
    """Feed it one telemetry record at a time via update(); it tracks the
    current flight phase, the full flight history, and phase-change events.
    """

    def __init__(self, on_phase_change: Optional[Callable[[FlightPhase, FlightPhase, Dict[str, Any]], None]] = None):
        self.phase = FlightPhase.FLIGHT_START
        self.history: List[Dict[str, Any]] = []
        self.phase_events: List[Dict[str, Any]] = []  # [{phase, elapsed_sec, time}]
        self.phase_start_index: Dict[FlightPhase, int] = {FlightPhase.FLIGHT_START: 0}
        self.on_phase_change = on_phase_change
        self._ground_elevation_ft: Optional[float] = None
        self._recent: deque = deque()  # (elapsed_sec, record) pairs within SUSTAIN_WINDOW_SEC

        self._record_phase_event(self.phase, elapsed_sec=0.0, time_str="")

    # -- public API -----------------------------------------------------

    def update(self, record: Dict[str, Any]) -> bool:
        """Feed one telemetry sample. Returns True if the phase changed."""
        self.history.append(record)
        self._recent.append((record["elapsed_sec"], record))
        self._prune_recent(record["elapsed_sec"])
        self._update_ground_reference(record)

        new_phase = self._next_phase(record)
        changed = new_phase != self.phase
        if changed:
            old_phase = self.phase
            self.phase = new_phase
            self.phase_start_index[new_phase] = len(self.history) - 1
            self._record_phase_event(new_phase, record["elapsed_sec"], record["time"])
            if self.on_phase_change:
                self.on_phase_change(old_phase, new_phase, record)
        return changed

    def phase_slice(self, phase: FlightPhase, next_phase: Optional[FlightPhase] = None) -> List[Dict[str, Any]]:
        """The history records belonging to `phase` (from its start up to the
        start of `next_phase`, or to the end of history if that phase never
        started or wasn't reached).
        """
        start = self.phase_start_index.get(phase)
        if start is None:
            return []
        end = self.phase_start_index.get(next_phase) if next_phase else None
        return self.history[start:end]

    def altitude_agl_ft(self, record: Dict[str, Any]) -> float:
        if self._ground_elevation_ft is None:
            return 0.0
        return record["altitude_ft"] - self._ground_elevation_ft

    def is_on_ground(self, record: Dict[str, Any]) -> bool:
        return self.altitude_agl_ft(record) <= GROUND_AGL_MARGIN_FT

    def sustained(self, predicate: Callable[[Dict[str, Any]], bool]) -> bool:
        """True if `predicate` has held for every sample in the last SUSTAIN_WINDOW_SEC seconds."""
        if not self._recent:
            return False
        return all(predicate(r) for _elapsed, r in self._recent)

    def save(self, flights_dir: str, session_name: Optional[str] = None) -> str:
        """Write the full recorded flight (history + phase timeline) as JSON."""
        os.makedirs(flights_dir, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        name = session_name or f"flight_{stamp}"
        path = os.path.join(flights_dir, f"{name}.json")
        payload = {
            "schema_fields": FIELD_NAMES,
            "phase_events": self.phase_events,
            "records": self.history,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return path

    # -- internals --------------------------------------------------------

    def _prune_recent(self, now_elapsed: float) -> None:
        while self._recent and now_elapsed - self._recent[0][0] > SUSTAIN_WINDOW_SEC:
            self._recent.popleft()

    def _update_ground_reference(self, record: Dict[str, Any]) -> None:
        ground_like_phase = self.phase in (
            FlightPhase.FLIGHT_START, FlightPhase.TAXI, FlightPhase.TAKEOFF_ROLL,
            FlightPhase.LANDING, FlightPhase.TAXI_IN, FlightPhase.SHUTDOWN,
        )
        if self._ground_elevation_ft is None:
            self._ground_elevation_ft = record["altitude_ft"]
        elif ground_like_phase and abs(record["vertical_speed_fpm"]) < 100:
            self._ground_elevation_ft = record["altitude_ft"]

    def _record_phase_event(self, phase: FlightPhase, elapsed_sec: float, time_str: str) -> None:
        self.phase_events.append({"phase": phase.value, "elapsed_sec": elapsed_sec, "time": time_str})

    def _next_phase(self, record: Dict[str, Any]) -> FlightPhase:
        phase = self.phase
        agl = self.altitude_agl_ft(record)
        on_ground = agl <= GROUND_AGL_MARGIN_FT

        if phase is FlightPhase.FLIGHT_START:
            if not record["parking_brake"] and (record["airspeed_kt"] > TAXI_MIN_KT or record["throttle_pct"] > 15):
                return FlightPhase.TAXI
            return phase

        if phase is FlightPhase.TAXI:
            if on_ground and record["throttle_pct"] >= TAKEOFF_THROTTLE_PCT and record["airspeed_kt"] > TAXI_MIN_KT:
                return FlightPhase.TAKEOFF_ROLL
            return phase

        if phase is FlightPhase.TAKEOFF_ROLL:
            if record["airspeed_kt"] >= ROTATION_SPEED_KT:
                return FlightPhase.ROTATION
            return phase

        if phase is FlightPhase.ROTATION:
            if not on_ground and record["vertical_speed_fpm"] > CLIMB_VS_THRESHOLD_FPM:
                return FlightPhase.CLIMB
            return phase

        if phase is FlightPhase.CLIMB:
            if self.sustained(lambda r: abs(r["vertical_speed_fpm"]) < CRUISE_VS_STABLE_FPM):
                return FlightPhase.CRUISE
            return phase

        if phase is FlightPhase.CRUISE:
            if self.sustained(lambda r: r["vertical_speed_fpm"] <= DESCENT_VS_THRESHOLD_FPM):
                return FlightPhase.DESCENT
            return phase

        if phase is FlightPhase.DESCENT:
            if agl <= APPROACH_AGL_FT and record["flaps_pct"] > 0:
                return FlightPhase.APPROACH
            return phase

        if phase is FlightPhase.APPROACH:
            if on_ground:
                return FlightPhase.LANDING
            return phase

        if phase is FlightPhase.LANDING:
            if on_ground and record["airspeed_kt"] <= TAXI_IN_MAX_KT:
                return FlightPhase.TAXI_IN
            return phase

        if phase is FlightPhase.TAXI_IN:
            if record["parking_brake"] and record["airspeed_kt"] < TAXI_MIN_KT:
                return FlightPhase.SHUTDOWN
            return phase

        return phase  # SHUTDOWN is terminal
