# Roadmap

Honest limitations of the current build, and what would need to change to
address each one. Ordered roughly by what would matter most for turning
this into a commercial-grade product, not by ease.

## Near-term (would unblock real training use)

- **Verify the C# Connector by actually compiling and flying it.** This is
  the single highest-priority item. Everything in `Connector/` was written
  without access to Windows, a `dotnet` toolchain, or the SimConnect SDK.
  The code follows documented SimConnect .NET patterns and the automatic
  analysis hand-off (`Process.Start("python", "run_pilotai.py --analyze ...")`)
  is straightforward, but none of it has ever been built, let alone run
  against a real simulator. Do this before the next demo, not during it.
  Also confirm the `PythonExecutable` constant in `Connector/Program.cs`
  matches the actual `python`/`python3` install on the demo PC.
- **Touch-and-go / multiple-landing support.** `Engine/flight_recorder.py`'s
  state machine is single-flight and forward-only: Shutdown is terminal,
  and `FlightEndDetector.cs` ends the recording on the first genuine
  engine-shutdown-while-parked it sees. Real training flights often do
  pattern work with several landings before a full stop. Supporting that
  needs a real design decision: detect a go-around (throttle-up and climb
  shortly after touchdown) and loop the phase machine back to Climb rather
  than advancing to Taxi In, and decide how that's scored and shown on the
  timeline.
- **Wind and crosswind telemetry.** The current simvar list has no wind
  speed/direction. `Engine/landing_analysis.py`'s `crosswind_correction`
  field is a heuristic from bank angle and heading alone. Adding
  `AMBIENT WIND VELOCITY` / `AMBIENT WIND DIRECTION` would let the Landing
  Analyzer compute a real crosswind component and grade the correction
  against it properly.
- **Instructor-reviewed thresholds.** Every number in `mistake_detector.py`
  and `landing_analysis.py` is a documented, defensible-but-generic Cessna
  172 estimate. Getting a CFI to review and adjust rotation speed,
  approach speed, bank limits, etc. against real training standards would
  make the scoring meaningfully more credible.

## Medium-term

- **More aircraft types.** Everything is currently tuned for (and labeled
  as) a Cessna 172 -- rotation speed, approach speed, climb performance,
  fixed gear. Supporting another aircraft means a per-aircraft threshold
  profile (rather than module-level constants), and the gear-related
  checklist/mistake logic actually mattering (right now it's wired up but
  inert, since the C172 never retracts its gear).
- **A trained model, once there's data.** The system deliberately uses a
  rules engine instead of ML (see `docs/ARCHITECTURE.md`) because there's
  no flight-training dataset yet. Once PilotAI has logged enough real
  flights with instructor-reviewed outcomes, a model trained on
  *disagreements* with the rules engine (not replacing it outright) could
  refine thresholds or catch patterns the fixed rules miss, while keeping
  the rules engine as an auditable baseline.
- **Local LLM summary, tested against a real model.** `LocalLLMSummaryBackend`
  is implemented and falls back safely, but hasn't been exercised against
  an actual running Ollama (or similar) instance in this environment.
  Worth doing once there's a machine with one installed.
- **Multi-session history and trends.** Right now every flight is scored
  independently. A student/aircraft-level history view ("your hard-landing
  rate over your last 10 flights") would need a small persistent store
  (SQLite would be a natural fit, and is zero-dependency) instead of just
  flat files in `Data/flights/`.

## Longer-term

- **Other simulators.** The architecture's split (a thin sim-specific
  Connector, a sim-agnostic Engine) was chosen partly so a future X-Plane
  or other-sim connector could feed the same analysis and report pipeline
  without touching it -- as long as it writes the same telemetry schema to
  a recording file and triggers `run_pilotai.py --analyze` the same way.
- **A previous, more ambitious version of this project** had a live web
  dashboard, voice coaching, and a TCP telemetry stream between the
  Connector and a long-running Python Engine process. That version is
  preserved in git history. If a future use case genuinely needs live
  in-flight feedback again (not just a post-flight report), that's the
  starting point to revive and adapt -- but see docs/ARCHITECTURE.md for
  why it was removed rather than kept running alongside this simpler
  pipeline.
