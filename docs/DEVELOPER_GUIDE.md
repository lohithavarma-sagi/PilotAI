# Developer Guide

## Codebase tour

```
Connector/            C# -- SimConnect, local recording, auto-analysis trigger (Windows + sim only)
  FlightRecord.cs         the shared data shape (mirrors Engine/telemetry_schema.py)
  SimConnectReader.cs     wraps SimConnect, self-throttles to the configured sample rate
  FakeFlightGenerator.cs  test-mode synthetic flight (mirrors Engine/synthetic_flight.py)
  FlightEndDetector.cs    "is this flight over?" heuristic (engine ran, then stopped + parked)
  TelemetryRecorder.cs    buffers + writes CSV/JSON to disk -- purely local, no networking
  Program.cs              entry point: connect-or-test-mode, auto-reconnect, auto-launch analysis

Engine/                Python -- phase detection, checklist, mistakes, scoring; no networking, no threads
  telemetry_schema.py     canonical field list + type coercion
  synthetic_flight.py     the one synthetic Cessna 172 flight profile, any sample rate
  flight_recorder.py      11-phase state machine (the "Flight Recorder")
  checklist_engine.py     phase checklists, missed/out-of-sequence detection
  stats_utils.py          shared stdev / circular-heading-stdev helpers
  mistake_detector.py     canonical mistake scanning: timestamp, category, severity, explanation, recommendation
  landing_analysis.py     landing-specific metrics (approach speed, descent rate, flare timing, ...)
  scoring_engine.py       converts mistake_detector's output into 8 category scores
  logging_setup.py        central logging config
  analyze.py              the batch pipeline: load -> replay -> checklist -> score (no live loop)

Reports/               Python -- turns a completed analysis into a report
  instructor_summary.py   template-based (default) + optional local-LLM summary generator
  report_builder.py       builds one structured report dict (single source of truth)
  json_report.py / pdf_report.py / text_report.py   three renderings of that one dict
  instructor_report.py    orchestrator: builds + saves all three, called by run_pilotai.py

Tests/                 unittest-based tests, run via Tests/run_all.py
run_pilotai.py          the one Python entry point: --test or --analyze FILE
```

## Running things while developing

```bash
python3 run_pilotai.py --test          # full pipeline, synthetic flight
python3 Tests/run_all.py               # everything, ~1s
python3 -m unittest Tests.test_mistake_detector   # one file
```

Every `Engine/*.py` module is directly runnable/importable stand-alone
(flat modules, no package `__init__.py`, by design -- see "Why flat
modules" below), so you can also poke at pieces individually:

```bash
cd Engine
python3 -c "
from synthetic_flight import generate_flight
from flight_recorder import FlightRecorder
r = FlightRecorder()
for rec in generate_flight(sample_interval=0.5, seed=1):
    r.update(rec)
print([e['phase'] for e in r.phase_events])
"
```

## Why flat modules, not Python packages

`Engine/` and `Reports/` are directories of plain `.py` files, not packages
with `__init__.py` and relative imports. Cross-directory imports use
`sys.path.insert(...)` at the top of entry-point scripts (`run_pilotai.py`,
`Tests/*.py`). This keeps every file importable and testable in isolation
with zero package-relative-import ceremony, at the cost of static analyzers
(Pylance etc.) not resolving the cross-directory imports -- a known,
harmless warning, not a bug.

## Extension points

**Add a mistake check** (`Engine/mistake_detector.py`): add a check inside
the relevant `evaluate_<phase>()` function (or add a new one for a new
phase), append a `Mistake` via the `_mistake()` helper on failure, and add
a matching `strengths.append(...)` on the passing path -- both scoring and
the "Detected Mistakes" report section come from the same evaluation, so
there's no second place to keep in sync. Every mistake needs a
`recommendation`, checked by
`Tests/test_scoring_engine.py::test_every_mistake_has_explanation_and_recommendation`.
If a check's threshold overlaps conceptually with another category (e.g.
"excessive bank" appears in both Cruise and Aircraft Control), that's fine
-- see `evaluate_aircraft_control`'s docstring for why the overlap is
intentional, not a duplicate-logic bug.

**Add a checklist item** (`Engine/checklist_engine.py`): add a
`ChecklistItem` to `_build_default_checklist()`. Set `not_before` to the
earliest `FlightPhase` the condition should be evaluated from -- skipping
this is the single most common bug in this file's history (several items
could trivially "complete" at `elapsed_sec=0` because the aircraft's
pre-flight default state happened to satisfy their condition; see
`Tests/test_checklist_engine.py::test_no_item_completes_before_its_gate_phase`,
which pins this down). Only add items backed by a real telemetry field --
see `README.md`'s note on why "trim set" isn't a checklist item.

**Add a scoring category**: severities already map to points via
`SEVERITY_POINTS` in `mistake_detector.py`; a new category in
`scoring_engine.py` just needs a `CategoryScore` and an `.apply()` call
against the matching `evaluate_...()` function's `PhaseEvaluation`.

**Add a telemetry field**: see [API.md](API.md#telemetry-schema) for the
four files that need to change together.

**Change the Instructor Summary**: edit `TemplateSummaryBackend` in
`Reports/instructor_summary.py` for the offline default. To point it at a
local LLM instead, see `LocalLLMSummaryBackend` and API.md's section on it
-- never add a call to a cloud/paid API here; that would contradict the
whole point of the local-first refactor (see docs/ARCHITECTURE.md).

**Change the PDF layout**: `Reports/pdf_report.py`'s `build_pdf()` builds a
flat `story` list of reportlab flowables in the required section order
(title page, flight info, scores, performance chart, timeline, mistakes,
recommendations, strengths, instructor summary, final grade); the footer
is drawn separately via `_draw_footer`, passed to `doc.build()` as
`onFirstPage`/`onLaterPages` so it appears on every page.

## Testing philosophy

`Tests/` uses stdlib `unittest`, not pytest -- one less dependency, and this
project's test count doesn't need pytest's fixture machinery. Most tests
drive the real modules against `Engine/synthetic_flight.py`'s deterministic
(seeded) synthetic flight rather than mocks, because the interesting bugs
found during development were all things a mock would have hidden:

- **Checklist trivial-completion bug**: several items could "complete" at
  `elapsed_sec=0` because the aircraft's default parked state happened to
  satisfy their condition. Pinned down in `test_checklist_engine.py`.
- **Phase-detection ground-roll false-positive**: ground roll's ~0 fpm
  vertical speed could be mistaken for "already leveled into cruise."
  Pinned down in `test_flight_recorder.py`.
- **Bounced-landing false positive**: `_detect_bounce` originally used
  `recorder.altitude_agl_ft()`, which reflects the ground-elevation
  reference *as it ended up after the whole flight was replayed*, not as
  it was at the moment of touchdown -- so ordinary sensor jitter during
  rollout looked like a bounce. Fixed by measuring against the touchdown
  sample's own altitude, with a two-consecutive-samples requirement.
  Pinned down across many seeds/rates in `test_mistake_detector.py`.
- **Category misattribution**: "excessive descent rate" and "incorrect
  speed" belong to the Approach category per spec, not Landing -- caught
  while writing `test_scoring_engine.py` against the actual spec text, not
  just against whatever the code already did.

If you touch `mistake_detector.py`, `scoring_engine.py`, or
`checklist_engine.py`, run the full suite, not just the file you think is
affected -- several of the bugs above were only visible from a different
file's test.

## What's *not* automatically testable here

`Connector/*.cs` has no automated tests and cannot be compiled in this
environment (no `dotnet`, no SimConnect SDK). If you're extending it,
build on the actual sim PC and test against a real simulator session before
trusting it.
