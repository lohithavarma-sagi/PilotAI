"""
mistake_detector.py

Canonical mistake detection for a completed flight. Scans a FlightRecorder's
phases once and returns, for each phase, the mistakes found (timestamp,
category, severity, explanation, recommendation) and the strengths (checks
that passed cleanly). This is the single source of truth for "what
happened and when" -- scoring_engine.py turns severities into point
deductions, and Reports/report_builder.py lists the same mistakes directly
under "Detected Mistakes". One detection pass, not two, so the report's
mistake list and the score can't describe the same moment differently.

This is a rules engine, not a trained model -- see scoring_engine.py's
docstring for why that's the deliberate choice here.

Thresholds are documented, generic Cessna 172 numbers (see README's "known
limitations"), not tuned to a specific POH or tail number.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from flight_recorder import FlightPhase, FlightRecorder
from landing_analysis import (
    analyze_landing,
    RECOMMENDED_APPROACH_SPEED_KT,
    RECOMMENDED_DESCENT_RATE_FPM,
    MAX_TOUCHDOWN_BANK_DEG,
)
from stats_utils import circular_heading_stdev, stdev

# --- Takeoff ---
ROTATION_SPEED_MIN_KT = 45.0
ROTATION_SPEED_MAX_KT = 65.0
TAKEOFF_FLAPS_MAX_PCT = 20.0
TAKEOFF_ROLL_HEADING_DRIFT_LIMIT_DEG = 8.0

# --- Climb ---
CLIMB_SMOOTHNESS_STDEV_LIMIT_FPM = 180.0
EXCESSIVE_CLIMB_RATE_FPM = 1200.0
CLIMB_MIN_SAFE_SPEED_KT = 60.0  # a margin below Vy (~73 KIAS) for a C172

# --- Cruise ---
ALTITUDE_STABILITY_LIMIT_FT = 150.0
CRUISE_AIRSPEED_STDEV_LIMIT_KT = 8.0
HEADING_STDEV_LIMIT_DEG = 8.0

# --- Shared / whole-flight ---
EXCESSIVE_BANK_LIMIT_DEG = 30.0
AGGRESSIVE_PITCH_LIMIT_DEG = 20.0

# --- Approach ---
UNSTABLE_APPROACH_VS_STDEV_FPM = 150.0
UNSTABLE_APPROACH_SPEED_STDEV_KT = 8.0
APPROACH_FLAPS_MIN_PCT = 20.0

# --- Landing ---
LATE_FLARE_LIMIT_SEC = 1.5
BOUNCE_AGL_THRESHOLD_FT = 8.0  # comfortably above normal telemetry noise (+/- a few ft), a real re-ascent, not sensor jitter
CENTERLINE_DEVIATION_LIMIT_DEG = 5.0

SEVERITY_POINTS = {"minor": 4, "moderate": 8, "major": 15}


@dataclass
class Mistake:
    elapsed_sec: float
    time: str
    phase: str
    category: str
    severity: str  # "minor" | "moderate" | "major"
    explanation: str
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "elapsed_sec": self.elapsed_sec,
            "time": self.time,
            "phase": self.phase,
            "category": self.category,
            "severity": self.severity,
            "explanation": self.explanation,
            "recommendation": self.recommendation,
        }


@dataclass
class PhaseEvaluation:
    mistakes: List[Mistake] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)


def _mistake(record: Dict[str, Any], phase: str, category: str, severity: str,
             explanation: str, recommendation: str) -> Mistake:
    return Mistake(record["elapsed_sec"], record["time"], phase, category, severity, explanation, recommendation)


def evaluate_takeoff(recorder: FlightRecorder) -> PhaseEvaluation:
    result = PhaseEvaluation()
    roll_slice = recorder.phase_slice(FlightPhase.TAKEOFF_ROLL, FlightPhase.ROTATION)
    rotation_slice = recorder.phase_slice(FlightPhase.ROTATION, FlightPhase.CLIMB)
    if not roll_slice or not rotation_slice:
        return result

    rotation_record = rotation_slice[0]
    rotation_speed_kt = rotation_record["airspeed_kt"]
    if rotation_speed_kt < ROTATION_SPEED_MIN_KT:
        result.mistakes.append(_mistake(
            rotation_record, "Takeoff", "early_rotation", "moderate",
            f"Rotated early at {rotation_speed_kt:.0f} kt, below the normal "
            f"{ROTATION_SPEED_MIN_KT:.0f}-{ROTATION_SPEED_MAX_KT:.0f} kt range -- risks a stall or a prolonged mush in ground effect.",
            "Hold the aircraft on the runway a moment longer and rotate at the recommended speed.",
        ))
    elif rotation_speed_kt > ROTATION_SPEED_MAX_KT:
        result.mistakes.append(_mistake(
            rotation_record, "Takeoff", "late_rotation", "minor",
            f"Rotated late at {rotation_speed_kt:.0f} kt, above the normal "
            f"{ROTATION_SPEED_MIN_KT:.0f}-{ROTATION_SPEED_MAX_KT:.0f} kt range -- uses more runway than necessary.",
            "Rotate closer to the recommended speed instead of carrying extra speed down the runway.",
        ))
    else:
        result.strengths.append(f"Rotated at {rotation_speed_kt:.0f} kt, within the normal range.")

    takeoff_flaps_pct = roll_slice[-1]["flaps_pct"]
    if takeoff_flaps_pct > TAKEOFF_FLAPS_MAX_PCT:
        result.mistakes.append(_mistake(
            roll_slice[-1], "Takeoff", "incorrect_flap_usage", "minor",
            f"Flaps were at {takeoff_flaps_pct:.0f}% for takeoff, above the normal "
            f"0-{TAKEOFF_FLAPS_MAX_PCT:.0f}% range.",
            "Set flaps within the normal takeoff range before starting the roll.",
        ))
    else:
        result.strengths.append("Flap configuration for takeoff was correct.")

    headings = [r["heading_deg"] for r in roll_slice]
    heading_drift = circular_heading_stdev(headings)
    if heading_drift > TAKEOFF_ROLL_HEADING_DRIFT_LIMIT_DEG:
        result.mistakes.append(_mistake(
            roll_slice[-1], "Takeoff", "takeoff_roll_drift", "minor",
            f"Heading wandered {heading_drift:.1f} degrees during the takeoff roll -- runway tracking could be tighter.",
            "Use rudder to track the centerline more precisely during the takeoff roll.",
        ))
    else:
        result.strengths.append("Tracked the runway centerline well during the takeoff roll.")

    # Cessna 172 has fixed (non-retractable) gear, so a "gear not retracted"
    # check is structurally a no-op for this airframe -- kept as a hook so
    # this evaluator works unmodified once a retractable-gear aircraft
    # profile exists (see docs/ROADMAP.md).

    return result


def evaluate_climb(recorder: FlightRecorder) -> PhaseEvaluation:
    result = PhaseEvaluation()
    climb_slice = recorder.phase_slice(FlightPhase.CLIMB, FlightPhase.CRUISE)
    if not climb_slice:
        return result

    vs_values = [r["vertical_speed_fpm"] for r in climb_slice]
    vs_stdev = stdev(vs_values)
    if vs_stdev > CLIMB_SMOOTHNESS_STDEV_LIMIT_FPM:
        result.mistakes.append(_mistake(
            climb_slice[len(climb_slice) // 2], "Climb", "rough_climb", "minor",
            f"Climb rate varied by {vs_stdev:.0f} fpm (stdev) -- pitch control could be smoother.",
            "Use smaller, smoother pitch adjustments during the climb to hold a steadier rate of climb.",
        ))
    else:
        result.strengths.append("Smooth, consistent climb rate.")

    peak_vs_record = max(climb_slice, key=lambda r: r["vertical_speed_fpm"])
    if peak_vs_record["vertical_speed_fpm"] > EXCESSIVE_CLIMB_RATE_FPM:
        result.mistakes.append(_mistake(
            peak_vs_record, "Climb", "excessive_climb_rate", "moderate",
            f"Climb rate reached {peak_vs_record['vertical_speed_fpm']:.0f} fpm, an aggressive pitch-up for a Cessna 172.",
            "Ease the pitch to hold a more moderate, sustainable climb rate.",
        ))

    slowest_record = min(climb_slice, key=lambda r: r["airspeed_kt"])
    if slowest_record["airspeed_kt"] < CLIMB_MIN_SAFE_SPEED_KT:
        result.mistakes.append(_mistake(
            slowest_record, "Climb", "low_airspeed", "major",
            f"Airspeed dropped to {slowest_record['airspeed_kt']:.0f} kt during the climb, below a safe margin.",
            "Lower the pitch attitude to keep airspeed comfortably above the climb reference speed.",
        ))
    else:
        result.strengths.append("Maintained a safe climb airspeed throughout.")

    max_bank_record = max(climb_slice, key=lambda r: abs(r["bank_deg"]))
    if abs(max_bank_record["bank_deg"]) > EXCESSIVE_BANK_LIMIT_DEG:
        result.mistakes.append(_mistake(
            max_bank_record, "Climb", "excessive_bank", "moderate",
            f"Bank reached {abs(max_bank_record['bank_deg']):.0f} degrees during the climb.",
            "Keep the wings level during the climb unless a turn is required.",
        ))

    return result


def evaluate_cruise(recorder: FlightRecorder) -> PhaseEvaluation:
    result = PhaseEvaluation()
    cruise_slice = recorder.phase_slice(FlightPhase.CRUISE, FlightPhase.DESCENT)
    if not cruise_slice:
        return result

    altitudes = [r["altitude_ft"] for r in cruise_slice]
    mean_altitude = sum(altitudes) / len(altitudes)
    worst_altitude_record = max(cruise_slice, key=lambda r: abs(r["altitude_ft"] - mean_altitude))
    altitude_deviation = abs(worst_altitude_record["altitude_ft"] - mean_altitude)
    if altitude_deviation > ALTITUDE_STABILITY_LIMIT_FT:
        result.mistakes.append(_mistake(
            worst_altitude_record, "Cruise", "altitude_deviation", "moderate",
            f"Cruise altitude varied by {altitude_deviation:.0f} ft from the average.",
            "Trim for level flight and make smaller pitch corrections to hold cruise altitude.",
        ))
    else:
        result.strengths.append("Held cruise altitude steady.")

    airspeeds = [r["airspeed_kt"] for r in cruise_slice]
    airspeed_stdev = stdev(airspeeds)
    if airspeed_stdev > CRUISE_AIRSPEED_STDEV_LIMIT_KT:
        result.mistakes.append(_mistake(
            cruise_slice[len(cruise_slice) // 2], "Cruise", "unstable_airspeed", "minor",
            f"Cruise airspeed varied by {airspeed_stdev:.1f} kt (stdev).",
            "Use smaller throttle and pitch adjustments to hold a steadier cruise airspeed.",
        ))
    else:
        result.strengths.append("Held a consistent cruise airspeed.")

    headings = [r["heading_deg"] for r in cruise_slice]
    heading_stdev = circular_heading_stdev(headings)
    if heading_stdev > HEADING_STDEV_LIMIT_DEG:
        result.mistakes.append(_mistake(
            cruise_slice[len(cruise_slice) // 2], "Cruise", "poor_heading_control", "moderate",
            f"Heading wandered during cruise (stdev {heading_stdev:.1f} degrees) -- course-keeping needs work.",
            "Pick a heading reference (a distant landmark or the heading bug) and correct drift earlier.",
        ))
    else:
        result.strengths.append("Good heading control / course-keeping.")

    max_bank_record = max(cruise_slice, key=lambda r: abs(r["bank_deg"]))
    if abs(max_bank_record["bank_deg"]) > EXCESSIVE_BANK_LIMIT_DEG:
        result.mistakes.append(_mistake(
            max_bank_record, "Cruise", "excessive_bank", "moderate",
            f"Bank angle reached {abs(max_bank_record['bank_deg']):.0f} degrees during cruise.",
            "Keep turns shallower (under 30 degrees of bank) unless a steep turn is intentional.",
        ))

    return result


def _get_landing_metrics(recorder: FlightRecorder) -> Tuple[Optional[Dict[str, Any]], Optional[int], Optional[int], Optional[int]]:
    landing_start = recorder.phase_start_index.get(FlightPhase.APPROACH)
    touchdown_idx = recorder.phase_start_index.get(FlightPhase.LANDING)
    rollout_end = recorder.phase_start_index.get(FlightPhase.TAXI_IN)
    if landing_start is None or touchdown_idx is None:
        return None, None, None, None
    landing_metrics = analyze_landing(recorder.history, landing_start, touchdown_idx, rollout_end)
    return landing_metrics, landing_start, touchdown_idx, rollout_end


def evaluate_approach(recorder: FlightRecorder) -> PhaseEvaluation:
    result = PhaseEvaluation()
    approach_slice = recorder.phase_slice(FlightPhase.APPROACH, FlightPhase.LANDING)
    if not approach_slice:
        return result

    vs_stdev = stdev([r["vertical_speed_fpm"] for r in approach_slice])
    speed_stdev = stdev([r["airspeed_kt"] for r in approach_slice])
    if vs_stdev > UNSTABLE_APPROACH_VS_STDEV_FPM or speed_stdev > UNSTABLE_APPROACH_SPEED_STDEV_KT:
        result.mistakes.append(_mistake(
            approach_slice[len(approach_slice) // 2], "Approach", "unstable_approach", "major",
            f"Approach was not stabilized -- sink rate varied by {vs_stdev:.0f} fpm and airspeed by {speed_stdev:.1f} kt.",
            "Get the aircraft configured and on speed earlier, then hold a constant power setting and descent rate to the runway.",
        ))
    else:
        result.strengths.append("Flew a stabilized approach.")

    last_record = approach_slice[-1]
    if last_record["flaps_pct"] < APPROACH_FLAPS_MIN_PCT:
        result.mistakes.append(_mistake(
            last_record, "Approach", "incorrect_flap_configuration", "moderate",
            f"Flaps were only at {last_record['flaps_pct']:.0f}% approaching the runway, below the normal landing configuration.",
            "Extend flaps to the normal landing setting during the approach, not at the last moment.",
        ))
    else:
        result.strengths.append("Correct flap configuration for landing.")

    landing_metrics, _start, touchdown_idx, _rollout_end = _get_landing_metrics(recorder)
    if landing_metrics is not None:
        touchdown_record = recorder.history[touchdown_idx]

        if landing_metrics["approach_speed_kt"] > RECOMMENDED_APPROACH_SPEED_KT:
            result.mistakes.append(_mistake(
                touchdown_record, "Approach", "incorrect_speed", "moderate",
                f"Approach speed averaged {landing_metrics['approach_speed_kt']} kt, above the "
                f"{RECOMMENDED_APPROACH_SPEED_KT:.0f} kt recommended reference.",
                "Reduce approach speed before touchdown -- aim closer to the recommended final-approach speed.",
            ))
        else:
            result.strengths.append(f"Approach speed ({landing_metrics['approach_speed_kt']} kt) was on target.")

        if landing_metrics["descent_rate_fpm"] <= RECOMMENDED_DESCENT_RATE_FPM:
            result.mistakes.append(_mistake(
                touchdown_record, "Approach", "excessive_descent_rate", "moderate",
                f"Descent rate on final averaged {landing_metrics['descent_rate_fpm']} fpm, "
                f"steeper than the {RECOMMENDED_DESCENT_RATE_FPM:.0f} fpm stabilized-approach guideline.",
                "Establish a stabilized approach earlier and reduce sink rate on final.",
            ))
        else:
            result.strengths.append("Final approach descent rate was within normal limits.")

    return result


def evaluate_landing(recorder: FlightRecorder) -> Tuple[PhaseEvaluation, Optional[Dict[str, Any]]]:
    result = PhaseEvaluation()
    landing_metrics, _start, touchdown_idx, rollout_end = _get_landing_metrics(recorder)
    if landing_metrics is None:
        return result, None

    touchdown_record = recorder.history[touchdown_idx]

    if landing_metrics["touchdown_quality"] == "hard":
        result.mistakes.append(_mistake(
            touchdown_record, "Landing", "hard_landing", "major",
            f"Hard touchdown at {landing_metrics['touchdown_vs_fpm']} fpm -- an excessive sink rate at the moment of touchdown.",
            "Flare a little later and hold it longer to reduce the sink rate at touchdown.",
        ))
    elif landing_metrics["touchdown_quality"] == "firm":
        result.mistakes.append(_mistake(
            touchdown_record, "Landing", "firm_landing", "minor",
            f"Firm touchdown at {landing_metrics['touchdown_vs_fpm']} fpm.",
            "A slightly longer flare would soften the touchdown further.",
        ))
    else:
        result.strengths.append("Smooth touchdown.")

    if landing_metrics["flare_timing_sec"] < LATE_FLARE_LIMIT_SEC:
        result.mistakes.append(_mistake(
            touchdown_record, "Landing", "late_flare", "moderate",
            f"Only {landing_metrics['flare_timing_sec']:.1f}s of flare before touchdown -- the round-out started late.",
            "Begin the flare a touch earlier and hold it through touchdown.",
        ))

    if landing_metrics["touchdown_bank_deg"] > MAX_TOUCHDOWN_BANK_DEG:
        result.mistakes.append(_mistake(
            touchdown_record, "Landing", "touchdown_bank", "minor",
            f"Aircraft was banked {landing_metrics['touchdown_bank_deg']} degrees at touchdown.",
            "Keep the wings level (or hold the correct crosswind correction) through touchdown.",
        ))

    if landing_metrics["runway_heading_deviation_deg"] >= CENTERLINE_DEVIATION_LIMIT_DEG:
        result.mistakes.append(_mistake(
            touchdown_record, "Landing", "runway_alignment", "moderate",
            f"Heading drifted {landing_metrics['runway_heading_deviation_deg']} degrees during rollout -- runway alignment could be tighter.",
            "Use rudder to track the centerline more precisely during rollout.",
        ))
    else:
        result.strengths.append("Tracked the runway centerline well through rollout.")

    bounced, bounce_agl_ft = _detect_bounce(recorder, touchdown_idx, rollout_end)
    if bounced:
        result.mistakes.append(_mistake(
            touchdown_record, "Landing", "bounced_landing", "major",
            f"The aircraft became airborne again ({bounce_agl_ft:.0f} ft AGL) shortly after the initial touchdown -- a bounced landing.",
            "Add a touch of power and hold a steady pitch attitude through a firm, single touchdown rather than trying to force it on.",
        ))

    # Cessna 172 has fixed gear, so a low-altitude "gear up" warning is
    # structurally a no-op for this airframe -- kept as a hook so this
    # evaluator works unmodified once a retractable-gear aircraft profile
    # exists (see docs/ROADMAP.md).
    if not touchdown_record["gear_down"]:
        result.mistakes.append(_mistake(
            touchdown_record, "Landing", "gear_warning", "major",
            "Landing gear was not down at touchdown.",
            "Complete the landing gear check before descending below traffic pattern altitude.",
        ))

    return result, landing_metrics


def _detect_bounce(recorder: FlightRecorder, touchdown_idx: int, rollout_end_idx: Optional[int]) -> Tuple[bool, float]:
    """A bounce is a re-ascent shortly after touchdown, measured against the
    touchdown sample's own altitude -- not recorder.altitude_agl_ft(), which
    uses the recorder's ground-elevation reference *as it ended up after the
    whole flight was replayed*, not as it was at this specific moment. Using
    that post-hoc value to judge a specific earlier sample was a real bug
    found while testing this function: it made the reference silently drift
    by however much ground-phase telemetry noise accumulated between
    touchdown and the end of the recording.

    A single noisy sample isn't a bounce -- telemetry can jitter by a few
    feet -- so this requires at least two consecutive samples above the
    threshold before calling it real.
    """
    end = rollout_end_idx if rollout_end_idx is not None else len(recorder.history)
    touchdown_altitude_ft = recorder.history[touchdown_idx]["altitude_ft"]
    window = recorder.history[touchdown_idx + 1:end]
    if len(window) < 2:
        return False, 0.0

    agl_values = [r["altitude_ft"] - touchdown_altitude_ft for r in window]
    for i in range(len(agl_values) - 1):
        if agl_values[i] > BOUNCE_AGL_THRESHOLD_FT and agl_values[i + 1] > BOUNCE_AGL_THRESHOLD_FT:
            return True, max(agl_values[i], agl_values[i + 1])
    return False, max(agl_values)


def evaluate_aircraft_control(recorder: FlightRecorder) -> PhaseEvaluation:
    """Whole-flight handling quality -- distinct from the phase-specific
    bank/pitch checks above. A single steep-bank moment in cruise can (and
    should) count against both Cruise's own score and this holistic
    Aircraft Control score; a real instructor's rubric would ding both a
    phase-specific box and an overall "aircraft handling" box for the same
    moment, so the overlap here is intentional, not double-counting a bug.
    """
    result = PhaseEvaluation()
    airborne_phases = (FlightPhase.CLIMB, FlightPhase.CRUISE, FlightPhase.DESCENT, FlightPhase.APPROACH)
    airborne_records = _records_in_phases(recorder, airborne_phases) or recorder.history
    if not airborne_records:
        return result

    max_bank_record = max(airborne_records, key=lambda r: abs(r["bank_deg"]))
    if abs(max_bank_record["bank_deg"]) > EXCESSIVE_BANK_LIMIT_DEG:
        result.mistakes.append(_mistake(
            max_bank_record, "Aircraft Control", "excessive_bank", "moderate",
            f"Maximum bank angle reached {abs(max_bank_record['bank_deg']):.0f} degrees during the flight.",
            "Keep turns shallower (under 30 degrees of bank) unless a steep turn is intentional.",
        ))
    else:
        result.strengths.append(f"Bank angle stayed within normal limits (max {abs(max_bank_record['bank_deg']):.0f} degrees).")

    max_pitch_record = max(airborne_records, key=lambda r: abs(r["pitch_deg"]))
    if abs(max_pitch_record["pitch_deg"]) > AGGRESSIVE_PITCH_LIMIT_DEG:
        result.mistakes.append(_mistake(
            max_pitch_record, "Aircraft Control", "aggressive_pitch", "minor",
            f"Pitch reached {abs(max_pitch_record['pitch_deg']):.0f} degrees at one point -- an aggressive attitude.",
            "Use smoother, smaller pitch inputs.",
        ))
    else:
        result.strengths.append(f"Pitch attitude stayed smooth (max {abs(max_pitch_record['pitch_deg']):.0f} degrees).")

    return result


def _records_in_phases(recorder: FlightRecorder, phases: Tuple[FlightPhase, ...]) -> List[Dict[str, Any]]:
    """Records belonging to any of `phases`, computed in one linear pass
    over history rather than a per-record phase lookup (which would be
    quadratic on a multi-thousand-sample flight).
    """
    boundaries = sorted(recorder.phase_start_index.items(), key=lambda kv: kv[1])
    result = []
    phase = FlightPhase.FLIGHT_START
    boundary_pos = 0
    for idx, record in enumerate(recorder.history):
        while boundary_pos < len(boundaries) and boundaries[boundary_pos][1] <= idx:
            phase = boundaries[boundary_pos][0]
            boundary_pos += 1
        if phase in phases:
            result.append(record)
    return result
