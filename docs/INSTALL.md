# Installing and Running PilotAI

PilotAI has two halves: the **Engine + Reports** (pure Python, runs
anywhere, no networking) and the **Connector** (C#, only runs on the
Windows PC where the simulator itself is installed). You can install and
use the Python half entirely on its own via `--test` mode -- useful for
rehearsing a demo, developing, or running the automated tests without ever
touching Windows or a simulator.

## 1. Python half (Engine, Reports, Tests)

Requirements: Python 3.8+.

```bash
python3 --version
pip install -r requirements.txt   # installs reportlab, for PDF report generation
```

That's the only third-party dependency in the whole Python codebase --
everything else (phase detection, scoring, checklist logic, file I/O) is
standard library only, by design: fewer things that can fail to install on
a demo floor, and nothing that talks to the network or costs money.

Run it in test mode (no simulator, no Connector):

```bash
python3 run_pilotai.py --test
```

This generates a synthetic Cessna 172 flight, analyzes it, and writes
`Data/flights/test_flight_..._report.pdf` (plus `.json` and `.txt`).

Analyze an already-recorded flight (e.g. one the Connector produced):

```bash
python3 run_pilotai.py --analyze Data/flights/flight_20260721_150000.json
```

Run the automated tests:

```bash
python3 Tests/run_all.py
```

## 2. C# Connector (Windows + the simulator, only)

The Connector needs to run on the same Windows PC as Microsoft Flight
Simulator or Prepar3D, since SimConnect only works locally.

> **This half is unverified by compilation.** It was written without
> access to Windows, a `dotnet` toolchain, or the SimConnect SDK. Build it
> and fix any compile errors *before* the day you need it -- see
> [README.md's Known Limitations](../README.md#known-limitations-read-this-before-demoing).

### 2.1 Prerequisites

1. Install the [.NET SDK](https://dotnet.microsoft.com/download) (6.0 or
   later; the project targets `net48` for SimConnect compatibility, which
   the modern SDK can still build as long as the .NET Framework 4.8
   targeting pack is present -- this normally ships with Visual Studio on
   Windows).
2. Install the SimConnect SDK:
   - **MSFS**: the [MSFS SDK](https://docs.flightsimulator.com/) installer.
   - **Prepar3D**: the Prepar3D SDK installer (bundled with the sim or
     downloadable separately).
3. Locate the managed SimConnect DLL, typically:
   ```
   MSFS:      C:\MSFS SDK\SimConnect SDK\lib\managed\Microsoft.FlightSimulator.SimConnect.dll
   Prepar3D:  C:\Prepar3D v5 SDK\SimConnect SDK\lib\managed\Microsoft.FlightSimulator.SimConnect.dll
   ```
4. Make sure `python` is on your `PATH` on the same PC (test with
   `python --version` in the same terminal you'll run the Connector from).
   `Connector/Program.cs` shells out to `python run_pilotai.py --analyze ...`
   automatically after every flight -- if your install is `python3` or a
   specific virtual environment's interpreter instead, edit the
   `PythonExecutable` constant near the top of `Connector/Program.cs`.

### 2.2 Build

Either edit the `SimConnectDllPath` property at the top of
`Connector/PilotAI.Connector.csproj` to match your install, or pass it at
build time without editing the file:

```bash
cd Connector
dotnet build -p:SimConnectDllPath="C:\MSFS SDK\SimConnect SDK\lib\managed\Microsoft.FlightSimulator.SimConnect.dll"
```

Then copy the **native** `SimConnect.dll` (a different file from the
managed wrapper above, found in the SDK's `lib\` folder) next to the built
`PilotAI.Connector.exe`. SimConnect will fail to connect at runtime without
it, even if the build succeeds.

### 2.3 Run

1. Start the simulator and load the Cessna 172.
2. Run the Connector:
   ```bash
   dotnet run --project Connector
   ```
3. That's it. From here on, everything is automatic:
   - It connects to the simulator via SimConnect and starts recording
     immediately.
   - If the simulator isn't running yet, it automatically falls back to a
     synthetic test flight (so the recording pipeline can still be
     demoed), and keeps retrying the real SimConnect connection between
     flights.
   - Once the student shuts the engine down (parking brake set, stopped,
     sustained for a few seconds), it stops recording and automatically
     runs `python run_pilotai.py --analyze` on the recording.
   - The PDF report appears in `Data/flights/` a few seconds later, with
     no further input needed.
   - It then waits, ready to record the next flight -- useful for a co-op
     demo booth where several people fly one after another without
     restarting the app.
   - If the simulator closes mid-session, it automatically retries the
     SimConnect connection instead of exiting.

## 3. Where everything gets saved

By default, everything lives under `Data/` in the repo:

```
Data/
  flights/   recorded flights (.json, .csv) and generated reports (.json/.pdf/.txt)
  logs/      pilotai.log (rotating, see docs/API.md's logging section)
```

Override the location with `--data-dir` when running `run_pilotai.py`
directly. (The Connector always uses the repo's `Data/flights/`.)
