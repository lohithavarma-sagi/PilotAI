"""
checklist_engine.py

Monitors a fixed set of checklist items against live telemetry, grouped
into the eight checklist phases from the spec: Engine Start, Taxi, Before
Takeoff, After Takeoff, Cruise, Approach, Landing, Shutdown.

Every item here is something we can actually detect from the telemetry
fields PilotAI reads (throttle, flaps, gear, parking brake, engine
combustion, autopilot master, fuel, vertical speed). We deliberately do NOT
include items like "trim set" or "mixture leaned" -- there's no simvar for
those in the current telemetry set, and a fake checklist item that always
silently passes (or worse, always fails) would be worse than not having it.
See docs/ROADMAP.md for what a v2 telemetry set would need to add to cover
those.

An item is:
  - completed on time, if its condition becomes true at or before its
    expected checklist phase ends
  - out of sequence, if its condition only becomes true after its expected
    phase has already ended
  - missed, if its condition never becomes true by the end of the flight
"""

from typing import Any, Callable, Dict, List, Optional

from flight_recorder import FlightPhase

CHECKLIST_PHASE_ORDER = [
    "Engine Start", "Taxi", "Before Takeoff", "After Takeoff",
    "Cruise", "Approach", "Landing", "Shutdown",
]

# Maps a checklist phase to the FlightPhase by whose START it must be satisfied.
_EXPECTED_BY_FLIGHT_PHASE = {
    "Engine Start": FlightPhase.TAXI,
    "Taxi": FlightPhase.TAKEOFF_ROLL,
    "Before Takeoff": FlightPhase.TAKEOFF_ROLL,
    "After Takeoff": FlightPhase.CRUISE,
    "Cruise": FlightPhase.DESCENT,
    "Approach": FlightPhase.LANDING,
    "Landing": FlightPhase.TAXI_IN,
    "Shutdown": None,  # only ever checked at the very end
}


class ChecklistItem:
    def __init__(self, item_id: str, checklist_phase: str, description: str,
                 condition: Callable[[Dict[str, Any]], bool], safety_critical: bool = False,
                 not_before: Optional[FlightPhase] = None):
        self.item_id = item_id
        self.checklist_phase = checklist_phase
        self.description = description
        self.condition = condition
        self.safety_critical = safety_critical
        # Some conditions (e.g. "flaps retracted" == flaps_pct == 0) are also
        # true of the aircraft's default pre-flight state, before the thing
        # being checked has happened even once. not_before gates evaluation
        # to start no earlier than a given flight phase, so those items can't
        # trivially "complete" at elapsed_sec 0.
        self.not_before = not_before
        self.completed = False
        self.out_of_sequence = False
        self.missed = False
        self.completed_at_elapsed_sec: Optional[float] = None
        self.completed_at_time: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.item_id,
            "phase": self.checklist_phase,
            "description": self.description,
            "safety_critical": self.safety_critical,
            "completed": self.completed,
            "out_of_sequence": self.out_of_sequence,
            "missed": self.missed,
            "completed_at_elapsed_sec": self.completed_at_elapsed_sec,
            "completed_at_time": self.completed_at_time,
        }


def _build_default_checklist() -> List[ChecklistItem]:
    return [
        ChecklistItem("engine_start_running", "Engine Start", "Engine running",
                      lambda r: r["engine_combustion"]),
        ChecklistItem("engine_start_brake_set", "Engine Start", "Parking brake set for engine start",
                      lambda r: r["parking_brake"] and r["engine_combustion"], safety_critical=True),

        ChecklistItem("taxi_brake_released", "Taxi", "Parking brake released for taxi",
                      lambda r: not r["parking_brake"] and r["airspeed_kt"] > 1.0),

        ChecklistItem("before_takeoff_flaps_set", "Before Takeoff", "Flaps set for takeoff (0-20%)",
                      lambda r: 0.0 <= r["flaps_pct"] <= 20.0),

        ChecklistItem("after_takeoff_positive_climb", "After Takeoff", "Positive rate of climb established",
                      lambda r: r["vertical_speed_fpm"] > 300, safety_critical=True, not_before=FlightPhase.ROTATION),
        ChecklistItem("after_takeoff_flaps_retracted", "After Takeoff", "Takeoff flaps retracted",
                      lambda r: r["flaps_pct"] == 0.0, not_before=FlightPhase.ROTATION),

        ChecklistItem("cruise_fuel_sufficient", "Cruise", "Fuel quantity checked and sufficient",
                      lambda r: r["fuel_qty_gal"] > 5.0, safety_critical=True, not_before=FlightPhase.CLIMB),

        ChecklistItem("approach_flaps_extended", "Approach", "Flaps extended for landing",
                      lambda r: r["flaps_pct"] >= 20.0, not_before=FlightPhase.DESCENT),
        ChecklistItem("approach_autopilot_off", "Approach", "Autopilot disengaged for landing",
                      lambda r: not r["autopilot_master"], safety_critical=True, not_before=FlightPhase.CRUISE),

        ChecklistItem("landing_brake_not_set", "Landing", "Parking brake not set at touchdown",
                      lambda r: not r["parking_brake"], safety_critical=True, not_before=FlightPhase.APPROACH),

        ChecklistItem("shutdown_brake_set", "Shutdown", "Parking brake set before shutdown",
                      lambda r: r["parking_brake"], not_before=FlightPhase.TAXI_IN),
        ChecklistItem("shutdown_engine_off", "Shutdown", "Engine shut down",
                      lambda r: not r["engine_combustion"], not_before=FlightPhase.TAXI_IN),
    ]


class ChecklistEngine:
    """Feed it (record, current_flight_phase) once per telemetry sample.
    Call finalize() once at the end of the flight to mark anything still
    outstanding as missed.
    """

    def __init__(self, items: Optional[List[ChecklistItem]] = None):
        self.items = items if items is not None else _build_default_checklist()
        self._flight_phase_order = {p: i for i, p in enumerate(FlightPhase)}
        self._current_flight_phase = FlightPhase.FLIGHT_START
        self.newly_completed: List[ChecklistItem] = []  # cleared and refilled each update(), for the live coach

    def update(self, record: Dict[str, Any], current_flight_phase: FlightPhase) -> None:
        self._current_flight_phase = current_flight_phase
        self.newly_completed = []
        for item in self.items:
            if item.completed or item.missed:
                continue
            if item.not_before is not None and self._phase_index(current_flight_phase) < self._phase_index(item.not_before):
                continue
            if not item.condition(record):
                continue
            item.completed = True
            item.completed_at_elapsed_sec = record["elapsed_sec"]
            item.completed_at_time = record["time"]
            expected_by = _EXPECTED_BY_FLIGHT_PHASE.get(item.checklist_phase)
            if expected_by is not None and self._phase_index(current_flight_phase) > self._phase_index(expected_by):
                item.out_of_sequence = True
            self.newly_completed.append(item)

    def finalize(self) -> None:
        """Call once the flight has ended (SHUTDOWN reached, or recording stopped)."""
        for item in self.items:
            if not item.completed:
                item.missed = True

    def _phase_index(self, phase: FlightPhase) -> int:
        return self._flight_phase_order.get(phase, 0)

    def summary(self) -> Dict[str, Any]:
        missed = [i.description for i in self.items if i.missed]
        out_of_sequence = [i.description for i in self.items if i.out_of_sequence]
        return {
            "items": [i.to_dict() for i in self.items],
            "missed": missed,
            "out_of_sequence": out_of_sequence,
            "completed_count": sum(1 for i in self.items if i.completed),
            "total_count": len(self.items),
        }
