"""
synthetic_flight.py

The one and only synthetic Cessna 172 flight profile. Used by:
  - Engine/telemetry_source.py's SyntheticTelemetrySource, to drive the live
    engine/coach/dashboard in real time when no simulator is connected
    (test mode).
  - Analyzer/generate_test_flight.py, kept as a thin backward-compatible
    wrapper for the old one-shot batch demo (see that file's docstring).

Deliberately built phase-by-phase (not one formula) because ground roll,
climb, cruise, descent, and landing each have a genuinely different
relationship between throttle/pitch/airspeed. The flight is intentionally
imperfect in a few specific ways (a brief steep-bank excursion in cruise, a
somewhat fast and steep landing) so PilotAI's scoring, checklist, and
coaching all have something real to react to -- a flawless flight would not
exercise most of this codebase.

Track (lat/lon) uses flat-earth dead reckoning from ground speed and
heading -- fine for a demo map plot, not for real navigation.
"""

import datetime as dt
import math
import random
from typing import Any, Dict, Iterator

START_LAT_DEG = 43.6777
START_LON_DEG = -79.6248
FIELD_ELEVATION_FT = 650.0
CRUISE_ALTITUDE_FT = 3500.0
CRUISE_AIRSPEED_KT = 112.0
ROTATION_SPEED_KT = 55.0
CRUISE_HEADING_DEG = 270.0
SIM_TIME_START_SEC = 14 * 3600  # 14:00:00Z


def _advance_position(lat_deg, lon_deg, heading_deg, ground_speed_kt, dt_sec):
    distance_nm = (ground_speed_kt / 3600.0) * dt_sec
    heading_rad = math.radians(heading_deg)
    delta_lat = (distance_nm / 60.0) * math.cos(heading_rad)
    delta_lon = (distance_nm / 60.0) * math.sin(heading_rad) / max(math.cos(math.radians(lat_deg)), 0.1)
    return lat_deg + delta_lat, lon_deg + delta_lon


def generate_flight(sample_interval: float = 0.5, seed: int = 42) -> Iterator[Dict[str, Any]]:
    """Yield telemetry dict records for one full synthetic flight, spaced
    `sample_interval` seconds apart (elapsed_sec-wise -- this does not sleep;
    callers that want real-time pacing add their own delay between calls).
    """
    rnd = random.Random(seed)
    t0 = dt.datetime.now().replace(microsecond=0)
    elapsed = 0.0
    lat, lon = START_LAT_DEG, START_LON_DEG
    heading = CRUISE_HEADING_DEG
    fuel = 40.0
    fuel_burn_per_sec = 10.0 / 3600.0
    sim_time = SIM_TIME_START_SEC

    def make(altitude, airspeed, vs, hdg, pitch, bank, throttle, flaps, gear_down,
             rpm, parking_brake, engine_on, autopilot, jitter=True):
        nonlocal elapsed, lat, lon, sim_time, fuel
        alt = altitude
        speed = max(airspeed, 0.0)
        hd = hdg
        if jitter:
            alt += rnd.uniform(-5, 5)
            speed += rnd.uniform(-1.0, 1.0)
            hd += rnd.uniform(-0.5, 0.5)
        lat, lon = _advance_position(lat, lon, hd, speed, sample_interval)
        record = {
            "time": (t0 + dt.timedelta(seconds=elapsed)).strftime("%H:%M:%S"),
            "elapsed_sec": round(elapsed, 2),
            "altitude_ft": round(alt, 1),
            "airspeed_kt": round(speed, 1),
            "vertical_speed_fpm": round(vs, 1),
            "heading_deg": round(((hd % 360) + 360) % 360, 1),
            "pitch_deg": round(pitch, 1),
            "bank_deg": round(bank, 1),
            "latitude_deg": round(lat, 6),
            "longitude_deg": round(lon, 6),
            "throttle_pct": round(max(0.0, min(100.0, throttle)), 1),
            "flaps_pct": round(max(0.0, min(100.0, flaps)), 1),
            "gear_down": gear_down,
            "rpm": round(rpm, 0),
            "fuel_qty_gal": round(max(fuel, 0.0), 2),
            "parking_brake": parking_brake,
            "engine_combustion": engine_on,
            "autopilot_master": autopilot,
            "sim_time_sec": round(sim_time, 1),
        }
        elapsed += sample_interval
        sim_time += sample_interval
        fuel -= fuel_burn_per_sec * sample_interval
        return record

    def n_samples(duration_sec):
        return max(1, int(round(duration_sec / sample_interval)))

    # --- Flight Start: engine start, parked, brake set ---
    n = n_samples(5)
    for i in range(n):
        engine_on = i >= n // 3  # engine catches partway through
        yield make(FIELD_ELEVATION_FT, 0, 0, CRUISE_HEADING_DEG, 0, 0, 0, 0, True, 800 if engine_on else 0,
                    True, engine_on, False, jitter=False)

    # --- Taxi: brake released, slow roll to the runway ---
    n = n_samples(30)
    for i in range(n):
        progress = i / max(n - 1, 1)
        yield make(FIELD_ELEVATION_FT, 12 + rnd.uniform(-2, 2), 0, CRUISE_HEADING_DEG + progress * 20,
                    0, 0, 25, 0, True, 1000, False, True, False)

    # --- Takeoff Roll: accelerate to rotation speed ---
    n = n_samples(15)
    for i in range(n):
        progress = i / max(n - 1, 1)
        speed = (ROTATION_SPEED_KT + 5) * progress
        throttle = 40 + 60 * progress
        rpm = 1000 + 1300 * progress
        yield make(FIELD_ELEVATION_FT, speed, 0, CRUISE_HEADING_DEG, 0, 0, throttle, 10, True, rpm, False, True, False)

    # --- Rotation: brief liftoff ---
    n = n_samples(3)
    for i in range(n):
        progress = i / max(n - 1, 1)
        yield make(FIELD_ELEVATION_FT + 15 * progress, ROTATION_SPEED_KT + 3, 300 * progress, CRUISE_HEADING_DEG,
                    7, 0, 95, 10, True, 2400, False, True, False)

    # --- Climb ---
    n = n_samples(60)
    for i in range(n):
        progress = i / max(n - 1, 1)
        alt = FIELD_ELEVATION_FT + (CRUISE_ALTITUDE_FT - FIELD_ELEVATION_FT) * progress
        vs = 650 * (1 - progress * 0.3)
        flaps = max(0.0, 10 - progress * 20)
        yield make(alt, 78 + rnd.uniform(-2, 2), vs, CRUISE_HEADING_DEG + progress * 3, 9 - 2 * progress, 0,
                    92, flaps, True, 2500, False, True, False)

    # --- Cruise, with one brief steep-bank excursion; autopilot engaged partway ---
    n = n_samples(180)
    excursion_start = int(n * 0.39)
    excursion_len = max(1, n_samples(4))
    autopilot_from = int(n * 0.5)
    for i in range(n):
        if excursion_start <= i < excursion_start + excursion_len:
            turn_progress = (i - excursion_start) / excursion_len
            bank = 34 * math.sin(turn_progress * math.pi)
            heading += bank * 0.02
        else:
            bank = rnd.uniform(-2, 2)
        autopilot = i >= autopilot_from
        yield make(CRUISE_ALTITUDE_FT, CRUISE_AIRSPEED_KT, rnd.uniform(-40, 40), heading, 2.5, bank, 68, 0, True,
                    2350, False, True, autopilot)

    # --- Descent ---
    n = n_samples(90)
    for i in range(n):
        progress = i / max(n - 1, 1)
        alt = CRUISE_ALTITUDE_FT - (CRUISE_ALTITUDE_FT - (FIELD_ELEVATION_FT + 800)) * progress
        speed = CRUISE_AIRSPEED_KT - 15 * progress
        autopilot = progress < 0.6  # pilot takes back manual control partway down
        yield make(alt, speed, -550, CRUISE_HEADING_DEG, -1.5, rnd.uniform(-3, 3), 45, 0, True, 2100,
                    False, True, autopilot)

    # --- Final approach: intentionally a bit fast and steep ---
    n = n_samples(60)
    for i in range(n):
        progress = i / max(n - 1, 1)
        alt = (FIELD_ELEVATION_FT + 800) - 750 * progress
        speed = 78 - 4 * progress
        flaps = 10 + 20 * progress
        vs = -760 + 20 * progress
        yield make(alt, speed, vs, CRUISE_HEADING_DEG, -2 + 3 * progress, rnd.uniform(-2, 2), 35, flaps, True,
                    1900, False, True, False)

    # --- Flare & touchdown: stays hard on purpose ---
    n = n_samples(7)
    for i in range(n):
        progress = i / max(n - 1, 1)
        alt = FIELD_ELEVATION_FT + 50 * (1 - progress)
        speed = 72 - 6 * progress
        vs = -340 + 10 * progress
        yield make(alt, speed, vs, CRUISE_HEADING_DEG, 4 + 4 * progress, 0, 20, 30, True, 1500,
                    False, True, False, jitter=False)

    # --- Landing rollout: decelerate from touchdown speed to taxi speed ---
    n = n_samples(10)
    for i in range(n):
        progress = i / max(n - 1, 1)
        speed = 66 * (1 - progress) + 30 * progress if progress < 1 else 30
        speed = max(30, 66 - 36 * progress)
        yield make(FIELD_ELEVATION_FT, speed, 0, CRUISE_HEADING_DEG, 0, 0, 0, 30, True, 1000,
                    False, True, False)

    # --- Taxi In ---
    n = n_samples(20)
    for i in range(n):
        progress = i / max(n - 1, 1)
        speed = max(0.0, 15 * (1 - progress))
        brake = progress >= 0.97
        yield make(FIELD_ELEVATION_FT, speed, 0, CRUISE_HEADING_DEG - progress * 15, 0, 0, 15, 0, True, 900,
                    brake, True, False)

    # --- Shutdown ---
    n = n_samples(5)
    for i in range(n):
        progress = i / max(n - 1, 1)
        engine_on = progress < 0.4
        rpm = 900 * (1 - progress) if engine_on else 0
        yield make(FIELD_ELEVATION_FT, 0, 0, CRUISE_HEADING_DEG, 0, 0, 0, 0, True, rpm,
                    True, engine_on, False, jitter=False)
