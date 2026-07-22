# API Documentation

PilotAI has no network API anymore -- see docs/ARCHITECTURE.md. This
document covers the telemetry schema, the CLI, and the report data shape
instead.

## Telemetry schema

The canonical field list lives in `Engine/telemetry_schema.py` (`FIELDS`).
Every telemetry sample -- from the Connector's recording, or synthetic from
`Engine/synthetic_flight.py` -- is a JSON object / Python dict with exactly
these fields:

| Field | Type | Unit | Meaning |
|---|---|---|---|
| `time` | string | - | wall-clock time of this sample, `HH:MM:SS` |
| `elapsed_sec` | number | s | seconds since recording started |
| `altitude_ft` | number | ft | indicated altitude |
| `airspeed_kt` | number | kt | indicated airspeed |
| `vertical_speed_fpm` | number | fpm | vertical speed |
| `heading_deg` | number | deg | magnetic heading |
| `pitch_deg` | number | deg | pitch, positive = nose up |
| `bank_deg` | number | deg | bank, positive = right wing down |
| `latitude_deg` | number | deg | aircraft latitude |
| `longitude_deg` | number | deg | aircraft longitude |
| `throttle_pct` | number | % | throttle lever position |
| `flaps_pct` | number | % | flaps handle position |
| `gear_down` | bool | - | landing gear extended (always `true` on the C172 -- fixed gear) |
| `rpm` | number | rpm | engine 1 RPM |
| `fuel_qty_gal` | number | gal | total fuel remaining |
| `parking_brake` | bool | - | parking brake set |
| `engine_combustion` | bool | - | engine 1 is firing (running) |
| `autopilot_master` | bool | - | autopilot master switch engaged |
| `sim_time_sec` | number | s | simulator zulu time, seconds since midnight |

If you add a field, add it to `telemetry_schema.py` first, then to
`Connector/FlightRecord.cs` (the struct and `ToJson()`/`ToCsvRow()`),
`Connector/SimConnectReader.cs` (the simvar registration), and
`Engine/synthetic_flight.py` (so `--test` mode keeps producing valid data).

## Flight recording file

Written by `Connector/TelemetryRecorder.cs` to `Data/flights/`, two formats:

- `flight_<timestamp>.json` -- a bare JSON array of telemetry samples.
- `flight_<timestamp>.csv` -- the same data as CSV, written incrementally
  during recording (so a crash mid-flight still leaves a usable partial
  file).

`Engine/analyze.py`'s `load_flight_records()` accepts either format, and
also accepts the wrapped shape `FlightRecorder.save()` writes
(`{"records": [...], "phase_events": [...]}`), for flights saved directly
from Python (e.g. in tests).

## Command-line interface

```bash
python3 run_pilotai.py --test                     # generate + analyze a synthetic flight
python3 run_pilotai.py --analyze FLIGHT.json      # analyze an already-recorded flight
python3 run_pilotai.py --analyze FLIGHT.csv       # CSV works too
```

Options:

| Flag | Meaning |
|---|---|
| `--seed N` | random seed for `--test` mode (repeatable synthetic flights) |
| `--sample-interval SEC` | sample spacing for `--test` mode, default 0.5 |
| `--data-dir DIR` | where `flights/` and `logs/` live, default `./Data` |
| `--use-llm-summary` | prefer a configured local LLM for the Instructor Summary (see below), falling back to the template automatically |

This is exactly what `Connector/Program.cs` calls automatically once
`FlightEndDetector` confirms the flight is over:
`python run_pilotai.py --analyze <path-to-recording>`.

## The full instructor report shape

Produced by `Reports/report_builder.py`'s `build_report()`, saved as JSON
by `Reports/json_report.py`, and rendered as PDF/text by
`Reports/pdf_report.py` / `Reports/text_report.py`:

```json
{
  "generated_at": "2026-07-21T19:00:08",
  "aircraft": "Cessna 172",
  "flight_summary": {
    "date": "2026-07-21", "start_time": "...", "end_time": "...",
    "duration_sec": 484.0, "duration_str": "8m 4s",
    "phases_reached": ["Flight Start", "Taxi", "..."],
    "max_altitude_ft": 3505.0, "max_airspeed_kt": 113.0,
    "min_fuel_qty_gal": 35.2, "track_distance_nm": 11.4, "sample_count": 970
  },
  "timeline": [{"elapsed_sec": 0.0, "time": "", "type": "phase", "text": "Phase: Flight Start"}],
  "scores": {"overall_score": 94, "categories": {"Takeoff": {"name": "Takeoff", "score": 100, "mistakes": [], "strengths": ["..."]}, "...": "..."}},
  "mistakes": [{"elapsed_sec": 446.5, "time": "21:15:18", "phase": "Landing", "category": "hard_landing", "severity": "major", "explanation": "...", "recommendation": "..."}],
  "strengths": ["Rotated at 52 kt, within the normal range.", "..."],
  "checklist": {"items": ["..."], "missed": [], "out_of_sequence": [], "completed_count": 12, "total_count": 12},
  "landing_metrics": {"approach_speed_kt": 75.0, "descent_rate_fpm": -744.6, "touchdown_vs_fpm": -334.6, "touchdown_quality": "hard", "flare_timing_sec": 14.0, "landing_distance_ft": 1052.0, "runway_heading_deviation_deg": 0.5, "crosswind_correction": "...", "instructor_comments": ["..."]},
  "suggestions": ["Flare a little later and hold it longer to reduce the sink rate at touchdown.", "..."],
  "final_grade": {"letter": "A", "label": "Excellent"},
  "instructor_summary": "This was an excellent flight in the Cessna 172. ...",
  "performance_series": {"elapsed_sec": [0, 1, 2], "altitude_ft": [650, 651, 652], "airspeed_kt": [0, 1, 2], "vertical_speed_fpm": [0, 0, 5]}
}
```

Each `mistake` carries exactly the fields the spec requires: timestamp
(`elapsed_sec` + `time`), `phase`/`category`, `severity`
(minor/moderate/major), `explanation`, and `recommendation`.

## Instructor Summary backend (optional local LLM)

`Reports/instructor_summary.py` exposes a small `SummaryBackend` interface:

- `TemplateSummaryBackend` -- the default. Deterministic, offline, free.
- `LocalLLMSummaryBackend` -- opt-in. Reads `PILOTAI_LLM_ENDPOINT` (e.g.
  `http://localhost:11434/api/generate` for Ollama) and `PILOTAI_LLM_MODEL`
  from the environment, or accepts them as constructor arguments. Any
  failure (not configured, server not running, timeout, bad response)
  falls back to the template silently -- a report must never fail to
  generate because of this.

```bash
export PILOTAI_LLM_ENDPOINT="http://localhost:11434/api/generate"
export PILOTAI_LLM_MODEL="llama3"
python3 run_pilotai.py --analyze FLIGHT.json --use-llm-summary
```

Without `--use-llm-summary` (the default), the template backend is used
directly and the environment variables are ignored.

## Logging

Configured by `Engine/logging_setup.py`. Every module logs via
`logging.getLogger("pilotai.<module>")`; output goes to both the console
and a rotating file at `Data/logs/pilotai.log` (5MB x 5 backups). Loggers
in use: `pilotai.launcher`, `pilotai.reports`, `pilotai.instructor_summary`.
