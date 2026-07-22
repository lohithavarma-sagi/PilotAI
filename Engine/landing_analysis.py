"""
landing_analysis.py

Canonical landing-phase analysis, used by both the live scoring engine
(Engine/scoring_engine.py, while the flight is happening or right after
touchdown) and the legacy batch analyzer (Analyzer/LandingAnalysis.py, now a
thin wrapper that imports from here -- see that file for why it still
exists). Landing gets its own module instead of a few lines inside the
scoring engine because it's where most of a student's actual mistakes show
up, and because it now needs to compute enough detail (distance, centerline
deviation, flare timing, crosswind handling) to generate real instructor
comments, not just a pass/fail number.

Recommended-value constants are deliberately conservative, generic Cessna
172 numbers, not tuned to a specific POH or tail number -- a v0.1 starting
point, documented as such in README.md.
"""

import math
from typing import Any, Dict, List, Optional

RECOMMENDED_APPROACH_SPEED_KT = 70.0
HARD_LANDING_VS_FPM = -250.0
FIRM_LANDING_VS_FPM = -180.0
RECOMMENDED_DESCENT_RATE_FPM = -700.0
MAX_TOUCHDOWN_BANK_DEG = 5.0
FLARE_DURATION_SEC = 5.0              # assumed flare duration for a light single like the C172
APPROACH_REFERENCE_WINDOW_SEC = 25.0  # how much of "before the flare" counts as the stabilized-approach reference
CENTERLINE_HEADING_DEVIATION_LIMIT_DEG = 5.0
FEET_PER_KNOT_SECOND = 1.68781  # 1 knot = 1.68781 ft/s


def _flare_start_index(landing_slice: List[Dict[str, Any]], descent_reference_fpm: float) -> int:
    """Walk backward from touchdown to find where the sink rate first
    started easing up relative to the stabilized-approach descent rate --
    that's the flare. Returns an index into landing_slice.
    """
    for i in range(len(landing_slice) - 1, -1, -1):
        if landing_slice[i]["vertical_speed_fpm"] < descent_reference_fpm - 50:
            return min(i + 1, len(landing_slice) - 1)
    return 0


def analyze_landing(records: List[Dict[str, Any]], landing_start_idx: int, touchdown_idx: int,
                     rollout_end_idx: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Compute landing-phase metrics.

    landing_start_idx: index where final approach begins.
    touchdown_idx: index of the first on-ground sample (moment of touchdown).
    rollout_end_idx: index where the rollout ends (e.g. slowed to taxi
        speed); defaults to the end of `records` if not given.
    """
    landing_slice = records[landing_start_idx:touchdown_idx + 1]
    if not landing_slice:
        return None

    # Windows are defined in real seconds (via elapsed_sec), not sample
    # counts -- telemetry can arrive anywhere from 0.25s to 1s apart
    # depending on the source, and a fixed sample count would cover a
    # different amount of real time (and silently change what counts as
    # "stabilized approach") depending on the rate.
    touchdown_time = landing_slice[-1]["elapsed_sec"]
    pre_flare_end_time = touchdown_time - FLARE_DURATION_SEC
    window_start_time = pre_flare_end_time - APPROACH_REFERENCE_WINDOW_SEC

    approach_reference = [r for r in landing_slice if window_start_time <= r["elapsed_sec"] < pre_flare_end_time]
    if not approach_reference:
        approach_reference = [r for r in landing_slice if r["elapsed_sec"] < pre_flare_end_time] or landing_slice

    approach_speed_kt = sum(r["airspeed_kt"] for r in approach_reference) / len(approach_reference)
    descent_rate_fpm = sum(r["vertical_speed_fpm"] for r in approach_reference) / len(approach_reference)

    touchdown_record = records[touchdown_idx]
    touchdown_vs_fpm = touchdown_record["vertical_speed_fpm"]
    touchdown_bank_deg = abs(touchdown_record["bank_deg"])
    touchdown_pitch_deg = touchdown_record["pitch_deg"]
    runway_heading_deg = touchdown_record["heading_deg"]

    if touchdown_vs_fpm <= HARD_LANDING_VS_FPM:
        touchdown_quality = "hard"
    elif touchdown_vs_fpm <= FIRM_LANDING_VS_FPM:
        touchdown_quality = "firm"
    else:
        touchdown_quality = "smooth"

    # Flare timing: how many seconds before touchdown the pilot started
    # arresting the sink rate.
    flare_idx = _flare_start_index(landing_slice, descent_rate_fpm)
    flare_timing_sec = round(landing_slice[-1]["elapsed_sec"] - landing_slice[flare_idx]["elapsed_sec"], 1)

    # Rollout / landing distance: integrate ground speed over the rollout,
    # rather than trust lat/lon (which drifts under our flat-earth dead
    # reckoning) -- speed integration is the more trustworthy signal here.
    rollout = records[touchdown_idx:rollout_end_idx] if rollout_end_idx else records[touchdown_idx:]
    landing_distance_ft = 0.0
    for i in range(1, len(rollout)):
        dt_sec = rollout[i]["elapsed_sec"] - rollout[i - 1]["elapsed_sec"]
        avg_speed_kt = (rollout[i]["airspeed_kt"] + rollout[i - 1]["airspeed_kt"]) / 2
        landing_distance_ft += avg_speed_kt * FEET_PER_KNOT_SECOND * dt_sec

    # Runway centerline deviation: we don't have a true runway/centerline
    # database from telemetry alone, so this approximates control-of-track
    # by how much heading wandered from the touchdown heading during
    # rollout -- a real, useful proxy, just not literal lateral feet.
    rollout_headings = [r["heading_deg"] for r in rollout] or [runway_heading_deg]
    heading_deviation_deg = max(abs(((h - runway_heading_deg + 180) % 360) - 180) for h in rollout_headings)

    # Crosswind correction: with no wind vector in the current telemetry set,
    # this is a heuristic from bank vs. heading at touchdown, not a direct
    # wind measurement -- documented as an approximation, not a placeholder.
    if touchdown_bank_deg > 2.0 and heading_deviation_deg < CENTERLINE_HEADING_DEVIATION_LIMIT_DEG:
        crosswind_correction = "wing-low correction held through touchdown"
    elif touchdown_bank_deg <= 2.0 and heading_deviation_deg >= CENTERLINE_HEADING_DEVIATION_LIMIT_DEG:
        crosswind_correction = "possible uncorrected drift at touchdown"
    else:
        crosswind_correction = "no significant crosswind correction needed or observed"

    smoothness_score = 100
    if touchdown_quality == "hard":
        smoothness_score -= 40
    elif touchdown_quality == "firm":
        smoothness_score -= 15
    if touchdown_bank_deg > MAX_TOUCHDOWN_BANK_DEG:
        smoothness_score -= 15
    if heading_deviation_deg >= CENTERLINE_HEADING_DEVIATION_LIMIT_DEG:
        smoothness_score -= 15
    smoothness_score = max(0, smoothness_score)

    comments = _generate_instructor_comments(
        approach_speed_kt, descent_rate_fpm, touchdown_vs_fpm, touchdown_quality,
        touchdown_bank_deg, heading_deviation_deg, flare_timing_sec,
    )

    return {
        "approach_speed_kt": round(approach_speed_kt, 1),
        "descent_rate_fpm": round(descent_rate_fpm, 1),
        "touchdown_vs_fpm": round(touchdown_vs_fpm, 1),
        "touchdown_bank_deg": round(touchdown_bank_deg, 1),
        "touchdown_pitch_deg": round(touchdown_pitch_deg, 1),
        "touchdown_quality": touchdown_quality,
        "flare_timing_sec": flare_timing_sec,
        "landing_distance_ft": round(landing_distance_ft, 0),
        "runway_heading_deviation_deg": round(heading_deviation_deg, 1),
        "crosswind_correction": crosswind_correction,
        "smoothness_score": smoothness_score,
        "instructor_comments": comments,
    }


def _generate_instructor_comments(approach_speed_kt, descent_rate_fpm, touchdown_vs_fpm, touchdown_quality,
                                   touchdown_bank_deg, heading_deviation_deg, flare_timing_sec) -> List[str]:
    comments = []

    if approach_speed_kt > RECOMMENDED_APPROACH_SPEED_KT:
        comments.append(
            f"Approach speed averaged {approach_speed_kt:.0f} kt, "
            f"{approach_speed_kt - RECOMMENDED_APPROACH_SPEED_KT:.0f} kt above the recommended reference -- "
            f"carry less energy over the fence."
        )
    else:
        comments.append(f"Approach speed ({approach_speed_kt:.0f} kt) was on target.")

    if descent_rate_fpm <= RECOMMENDED_DESCENT_RATE_FPM:
        comments.append(
            f"Final approach sink rate averaged {descent_rate_fpm:.0f} fpm -- steeper than the "
            f"{RECOMMENDED_DESCENT_RATE_FPM:.0f} fpm stabilized-approach guideline. Get established earlier."
        )
    else:
        comments.append("Final approach was stabilized -- descent rate stayed within a normal range.")

    if touchdown_quality == "hard":
        comments.append(f"Touchdown was hard ({touchdown_vs_fpm:.0f} fpm) -- flare a little later and hold it longer.")
    elif touchdown_quality == "firm":
        comments.append(f"Touchdown was firm ({touchdown_vs_fpm:.0f} fpm) -- a slightly longer flare would smooth this out.")
    else:
        comments.append(f"Touchdown was smooth ({touchdown_vs_fpm:.0f} fpm).")

    if touchdown_bank_deg > MAX_TOUCHDOWN_BANK_DEG:
        comments.append(f"{touchdown_bank_deg:.0f} degrees of bank at touchdown -- get the wings level before the wheels touch.")

    if heading_deviation_deg >= CENTERLINE_HEADING_DEVIATION_LIMIT_DEG:
        comments.append(f"Heading wandered {heading_deviation_deg:.0f} degrees during rollout -- work on centerline tracking after touchdown.")
    else:
        comments.append("Centerline tracking through rollout was solid.")

    if flare_timing_sec < 1.0:
        comments.append("Very little flare before touchdown -- start rounding out a touch earlier.")

    return comments
