# PilotAI

A local, offline flight-instructor assistant for a Cessna 172 in Microsoft
Flight Simulator / Prepar3D. A student flies a short flight (~5 minutes);
the moment the engine is shut down, PilotAI automatically analyzes the
recording and generates a professional, printable instructor PDF report --
no manual steps, no server, no internet connection required.

```
Microsoft Flight Simulator
   |
   | SimConnect
   v
Connector/ (C#, Windows + sim only)
   - connects, auto-records from the moment it connects
   - detects engine shutdown -> stops recording
   - automatically runs: python run_pilotai.py --analyze <recording>
   v
Engine/ (Python) -- replay + phase detection + checklist + mistake
                    detection + scoring, all in one local batch pass
   v
Reports/ (Python) -- instructor summary + JSON + PDF + text report
```

No web dashboard, no live voice coaching, no networking beyond the local
SimConnect connection, no cloud services, nothing paid. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full reasoning behind
this shape and what an earlier, more ambitious version of PilotAI looked
like before this refactor.

## Quick start

Try the whole pipeline right now with no simulator:

```bash
pip install -r requirements.txt
python3 run_pilotai.py --test
```

This generates a synthetic ~8-minute Cessna 172 flight, analyzes it, and
writes `Data/flights/test_flight_..._report.pdf` (plus `.json` and `.txt`).
That's the same pipeline a real recorded flight goes through -- see
[docs/INSTALL.md](docs/INSTALL.md) for connecting the C# Connector to a
real simulator session, where the whole thing runs automatically the
moment the engine is shut down.

## What's here

| Folder | What it does | Runs on |
|---|---|---|
| `Connector/` | SimConnect, auto-record, auto-detect flight end, auto-launch analysis | Windows, with the sim |
| `Engine/` | Phase detection, checklist tracking, mistake detection, scoring | Any OS |
| `Reports/` | Instructor summary + JSON/PDF/text report generation | Any OS |
| `Tests/` | Automated tests for all of the above | Any OS |
| `Data/` | Recorded flights, generated reports, logs, nothing else | - |

Only `Connector/` needs Windows and the simulator. Everything else --
including the entire `--test` path -- runs anywhere Python does.

## Documentation

- [docs/INSTALL.md](docs/INSTALL.md) -- installing and running both halves
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) -- how the pieces fit together and why
- [docs/API.md](docs/API.md) -- telemetry schema, report shape, module reference
- [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) -- codebase tour, how to extend it
- [docs/ROADMAP.md](docs/ROADMAP.md) -- known limitations and what's next

## Known limitations (read this before demoing)

- **The C# Connector is unverified by compilation.** It was developed
  without access to Windows, MSFS/Prepar3D, or the SimConnect SDK -- there
  is no `dotnet` toolchain or SimConnect DLL available in this development
  environment. Build it on the actual sim PC before the demo and budget
  time to fix any compile-time surprises.
- **Cessna 172 has fixed gear.** "Gear not retracted" / "gear warning"
  checks will never fire for this airframe; they're wired up so the same
  code works unmodified on a retractable-gear aircraft.
- **One continuous flight per recording**, forward-only through 11 phases
  (Flight Start through Shutdown). Touch-and-goes and multiple landings in
  one session aren't modeled yet -- see [docs/ROADMAP.md](docs/ROADMAP.md).
- **No wind/crosswind telemetry.** Crosswind-correction commentary is a
  heuristic from bank angle and heading, not a true wind measurement.
- **Rules engine, not a trained model.** Every threshold is a documented,
  tunable constant (see `Engine/mistake_detector.py`, `Engine/scoring_engine.py`),
  not a machine-learned one -- see docs/ARCHITECTURE.md for why that's the
  deliberate choice for a report an instructor needs to be able to trust.
- **Instructor Summary is template-based by default**, fully offline and
  free. It can optionally use a *local* LLM (e.g. Ollama) if one is
  configured -- see `Reports/instructor_summary.py` -- but that's opt-in and
  never a cloud/paid dependency; if it's not configured or not reachable,
  generation falls back to the template automatically.
