"""
telemetry_schema.py

The single source of truth for what a "telemetry sample" is. Every other
module -- the live TCP feed from the C# Connector, the synthetic test-flight
generator, the flight recorder, the scoring engine, the dashboard -- reads
and writes this exact shape. If you add a simvar, add it here first, then
wire it into Connector/FlightRecord.cs (to match) and
Engine/telemetry_source.py's fake generator.

Field name -> (Python type, unit, plain-English description). Kept as a
list of tuples (not a dict) so field order is stable for CSV output.
"""

from typing import Any, Dict

FIELDS = [
    ("time", str, "-", "wall-clock time of this sample, HH:MM:SS"),
    ("elapsed_sec", float, "s", "seconds since recording started"),
    ("altitude_ft", float, "ft", "indicated altitude"),
    ("airspeed_kt", float, "kt", "indicated airspeed"),
    ("vertical_speed_fpm", float, "fpm", "vertical speed"),
    ("heading_deg", float, "deg", "magnetic heading"),
    ("pitch_deg", float, "deg", "pitch, positive = nose up"),
    ("bank_deg", float, "deg", "bank, positive = right wing down"),
    ("latitude_deg", float, "deg", "aircraft latitude"),
    ("longitude_deg", float, "deg", "aircraft longitude"),
    ("throttle_pct", float, "%", "throttle lever position"),
    ("flaps_pct", float, "%", "flaps handle position"),
    ("gear_down", bool, "-", "landing gear extended"),
    ("rpm", float, "rpm", "engine 1 RPM"),
    ("fuel_qty_gal", float, "gal", "total fuel remaining"),
    ("parking_brake", bool, "-", "parking brake set"),
    ("engine_combustion", bool, "-", "engine 1 is firing (running)"),
    ("autopilot_master", bool, "-", "autopilot master switch engaged"),
    ("sim_time_sec", float, "s", "simulator zulu time, seconds since midnight"),
]

FIELD_NAMES = [f[0] for f in FIELDS]
FIELD_TYPES: Dict[str, type] = {f[0]: f[1] for f in FIELDS}


def empty_record() -> Dict[str, Any]:
    """A zeroed-out record, useful as a base for tests and defaults."""
    record = {}
    for name, py_type, _unit, _desc in FIELDS:
        if py_type is bool:
            record[name] = False
        elif py_type is str:
            record[name] = ""
        else:
            record[name] = 0.0
    return record


def coerce_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce a dict of possibly-stringified values (e.g. from CSV or a
    minimal JSON sender) into the correct Python types. Missing fields are
    filled from empty_record() rather than raising, since a partial sample
    from a flaky connection is still worth having.
    """
    base = empty_record()
    for name, py_type, _unit, _desc in FIELDS:
        if name not in raw or raw[name] is None:
            continue
        value = raw[name]
        if py_type is bool:
            if isinstance(value, str):
                base[name] = value.strip().lower() in ("1", "true", "yes")
            else:
                base[name] = bool(value)
        elif py_type is str:
            base[name] = str(value)
        else:
            base[name] = float(value)
    return base
