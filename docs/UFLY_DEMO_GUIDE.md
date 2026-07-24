# PilotAI @ UFly — Deployment, Test Plan, and Demo Guide

This is the offline reference for testing and presenting PilotAI at UFly.
Bring this file (or a printout) in case Wi-Fi is unreliable on-site.

**Confirmed target environment:** Prepar3D **4.5.13.32097**, SimConnect
**4.5.0.0**. The simvars PilotAI reads (`INDICATED ALTITUDE`,
`AIRSPEED INDICATED`, `PLANE PITCH DEGREES`, etc. -- see
`Connector/SimConnectReader.cs`) are all core simvars that have existed
since FSX and are unchanged in P3D v4, so there is no telemetry
compatibility risk with this version. `Connector/PilotAI.Connector.csproj`
is configured for this environment: `net48` target, `x64` platform (P3D v4
is 64-bit-only), and defaults its `SimConnectDllPath` at the Prepar3D v4
SDK location.

## 1. Architecture: can PilotAI run with the Mac + UFly's Windows sim PC?

**The hard constraint:** SimConnect's client library only runs on Windows.
The C# Connector can never run directly on macOS, no matter the network
setup. What *is* possible (and has been supported since FSX): the
Connector running on a *different* Windows machine than the one running
Prepar3D, talking to it over the LAN. So "PilotAI on my Mac" is achievable
for the analysis + PDF half; the Connector half needs some Windows
environment -- just not necessarily the UFly desktop.

```
UFly Windows PC                         Your side
+------------------+                    +---------------------------+
| Prepar3D          |                    | Connector.exe (Windows)   |
| SimConnect SERVER  | <--- LAN/WiFi ---> | SimConnect CLIENT          |
| (built into P3D)   |    TCP/IPv4        | records + detects shutdown |
+------------------+                    | -> python run_pilotai.py   |
                                          +---------------------------+
```

### Three options, best to safest

| Option | Where the Connector runs | UFly PC needs | Fully automatic? |
|---|---|---|---|
| **A. Windows laptop you bring** | Your Windows laptop, full stack | One config file | Yes |
| **B. Windows VM on your Mac** | Free VM (VirtualBox/UTM/Parallels) on your Mac | Same one config file | Yes |
| **C. Portable .exe on the UFly PC** | UFly's desktop, from a USB stick, no installer | Nothing | No -- one manual file copy |

**Recommendation: plan for C, hope for A/B.** C is what's already built,
and has zero network variables to debug live. A/B are more impressive and
fully automatic but carry real unknowns (firewall, Wi-Fi client isolation)
you can't fully test in advance.

### Config files needed for A/B

Two ready-to-use templates are tracked in the repo at
`Connector/config-templates/` -- copy each one to its destination below and
rename it (dropping the `.template` suffix). Neither file is committed to
git with a real IP in it (`Data/config/` -- where the real, filled-in copy
should live if it stays on this machine -- is gitignored on purpose, since
it's machine-specific).

**On the UFly PC** (where Prepar3D runs), copy
`Connector/config-templates/SimConnect.xml.template` to:
```
%ProgramData%\Lockheed Martin\Prepar3D v4\SimConnect.xml
```
(this is the confirmed path for Prepar3D 4.5.13.32097). If that file
already exists with other `<SimConnect.Comm>` blocks in it from another
add-on, add this one alongside them -- don't delete existing entries.

**On the Connector's machine** (wherever `PilotAI.Connector.exe` runs from,
if that's a different PC than the one above), copy
`Connector/config-templates/SimConnect.cfg.template` to `SimConnect.cfg`
next to the built `.exe`, and replace `UFLY_SIM_PC_LOCAL_IPV4` with the
sim PC's actual local IPv4 address (get this from UFly directly, e.g. via
`ipconfig` on the sim PC itself -- don't guess it).

**No code changes needed for either file.** `SimConnectReader.cs` already
opens SimConnect with config index 0
(`new SimConnect(AppName, IntPtr.Zero, 0, _simConnectEvent, 0)`), which
makes the SimConnect DLL itself read the `[SimConnect]` section of
`SimConnect.cfg` -- pointing that one entry at the remote address is the
entire mechanism, handled by SimConnect itself, not by PilotAI's code.

If the Connector runs directly on the same PC as Prepar3D (the
recommended first test, option C below), **neither file is needed at
all** -- SimConnect defaults to a local connection with no config file
present.

### Quick answers

- **Anything installed on the UFly PC?** No installer -- just the one
  `SimConnect.xml` text file, which needs explicit permission.
- **Does Prepar3D already support this?** Yes, built in; the config file
  just turns on a capability that's already there.
- **What to ask UFly for:** the sim PC's LAN IP, confirmation Wi-Fi client
  isolation is off, firewall permission for the chosen port, permission to
  add the config file.
- **Works without internet?** Yes -- pure LAN traffic, no DNS/cloud needed.
- **Does PilotAI need a server?** No -- Prepar3D's own built-in SimConnect
  server is what's listening; PilotAI has zero server components.
- **Cost?** Zero. No subscriptions, no hosting, nothing paid.

## 2. How the report system works

**PDF generation via `reportlab`** (open-source Python library, the one
third-party dependency in the project) -- not Word, not Google Docs.
`Reports/pdf_report.py` builds the PDF programmatically and writes real
PDF bytes directly to disk.

- **Saved to:** `Data/flights/<flight-name>_report.pdf` (plus `.json` and
  `.txt` siblings).
- **Opening it:** any standard PDF viewer (Preview on Mac, Edge/Adobe on
  Windows) -- it's a completely standard file.
- **Printing it:** the OS's normal print dialog (⌘P / Ctrl+P).

## 3. Test plan

### Before UFly
```bash
pip install -r requirements.txt
python3 run_pilotai.py --test        # should finish in well under a second
python3 Tests/run_all.py             # all 30 should pass
```
Open and actually print the resulting PDF once. If you have access to any
Windows machine, try `dotnet build` in `Connector/` even without Prepar3D
installed -- confirming it compiles rules out the biggest unknown.

**Bring:** laptop with the repo + deps already installed, a USB drive with
the built Connector (if attempting option C) and a repo backup, a
pre-generated sample PDF (your insurance policy if nothing else works),
and this guide offline.

**Commands to know:**
```bash
python3 run_pilotai.py --test
python3 run_pilotai.py --analyze <flight_file>
dotnet run --project Connector        # Windows only
```

### At UFly

| Step | Action | Expected result |
|---|---|---|
| 1 | Connect both machines to the same network (only if Connector and Prepar3D are on different PCs -- see Option A/B/C above) | Both get an IP on the same subnet |
| 2 | Open Prepar3D, load the Cessna 172 | Sim running |
| 3 | Start the Connector (`dotnet run --project Connector`, or the built `.exe`) | `"PilotAI Connector starting..."` |
| 4 | Confirm connection | `"Connected to the simulator. Recording will start now and stop automatically after engine shutdown."` |
| 5 | Verify telemetry | `Data/flights/*.csv` growing with sensible, changing altitude/airspeed values |
| 6 | Fly ~5 minutes | Taxi, takeoff, cruise, land |
| 7 | Shut engine down, brake set, wait ~3s | `"Engine shutdown detected -- flight complete."` |
| 8 | Answer the two prompts in the same console | `Student Pilot Name:` then `Instructor/Supervisor Name:` |
| 9 | Wait for analysis | `"Report generated successfully."` (seconds, not minutes) |
| 10 | PDF opens automatically | Also printed in the console's completion banner: full path to the PDF, JSON, and text files |
| 11 | Print it | Standard print dialog |

## Pre-Flight Checklist

Run through this before the student gets in the seat:

- [ ] Prepar3D is running, Cessna 172 loaded, aircraft on the ramp/runway (not already airborne)
- [ ] If Connector and Prepar3D are on different PCs: both machines pingable on the same subnet, `SimConnect.xml` in place on the sim PC, `SimConnect.cfg` in place next to `PilotAI.Connector.exe` with the correct IP (see "Config files needed for A/B" above)
- [ ] `PilotAI.Connector.exe` builds/runs without error and prints `"PilotAI Connector starting..."`
- [ ] Console shows `"Connected to the simulator..."` -- **not** the TEST MODE fallback message (that means SimConnect didn't actually connect)
- [ ] `Data/flights/` is writable and has free disk space
- [ ] You know the Student Pilot Name and Instructor/Supervisor Name you'll type in when prompted
- [ ] A backup: a pre-generated sample PDF on hand, in case anything fails live

## Post-Flight Checklist

After the engine is shut down and the parking brake set:

- [ ] Console printed `"Engine shutdown detected -- flight complete."`
- [ ] Student Pilot Name / Instructor Name prompts answered
- [ ] Console printed `"Report generated successfully."` and the completion banner with file paths
- [ ] PDF opened automatically (or open it manually from the printed path if not)
- [ ] Confirm all three files exist: `_report.pdf`, `_report.json`, `_report.txt`, next to the original `.json`/`.csv` recording in `Data/flights/`
- [ ] Skim the PDF: title page names are correct, overall score and category scores look sane, at least one specific mistake has a timestamp and recommendation
- [ ] If anything looks wrong, check `Data/logs/pilotai.log` before re-flying

## 4. Demo script

**30-second pitch:** "PilotAI is a flight-instructor assistant for flight
simulators. A student flies a short flight, and the moment they shut the
engine down, PilotAI automatically analyzes takeoff through landing,
detects specific mistakes with timestamps and explanations, scores it
across seven categories, and generates a printable instructor PDF. No
cloud, no subscriptions, everything runs locally."

**2-minute demo:** folder structure (15s) -> fly or replay a flight (15s)
-> walk through the PDF: scores, one specific mistake with its timestamp
and recommendation, the instructor summary (30s) -> `Tests/run_all.py`
passing (30s) -> close on the local-only, zero-cost architecture (30s).

**What to say:** be direct about what's proven vs. not -- "The analysis
engine is fully built and tested, 30 passing automated tests, several
caught real bugs during development. The one piece I haven't verified is
the SimConnect connector, since I built this without a Windows machine
with Prepar3D. That's the concrete next step."

**Show:** the PDF, the passing tests, one specific mistake finding, that it
runs in under a second with no internet.

**Avoid:** promising the live SimConnect link works if untested; calling
the scoring "AI" in the ML sense if pressed (it's a rules engine --
say so, it's a strength: auditable, no training data needed); diving into
C# internals unless asked.

### Demonstrating PilotAI to your supervisor

A concrete run-through, in order:

1. **Set the stage (30s).** Give the 30-second pitch above before touching
   the keyboard -- your supervisor should know what they're about to watch
   before they watch it.
2. **Fly the real thing.** Start the Connector, fly a real ~5-minute
   pattern (or a short local flight) in front of them, and narrate the
   automatic parts as they happen: "it's recording now, no button I
   pressed for that" / "I just shut the engine down -- watch." This is
   more convincing live than any slide.
3. **Answer the two prompts on camera.** Type the student's real name and
   your supervisor's name (or their own, if they want to see it) when
   prompted -- it's a nice, concrete "this report is really about this
   flight" moment.
4. **Let the PDF open itself.** Don't open it manually -- let the
   auto-open feature do it, and narrate that too.
5. **Walk the PDF top to bottom** (60-90s): title page (names, date,
   duration) -> executive summary (overall score, letter grade, one-line
   verdict) -> category scores table -> one specific Key Mistake, read its
   timestamp/explanation/recommendation aloud -> strengths -> instructor
   summary paragraph.
6. **Show `Tests/run_all.py` passing** (30s) as evidence the analysis logic
   itself is tested, not just eyeballed.
7. **Close on the constraints that matter to a supervisor:** runs fully
   offline, no per-flight cost, no student data leaves the building, and
   the scoring is a rules engine (auditable, not a black box) -- these are
   usually the first questions a supervisor asks, so answering them before
   they're asked lands well.

If you can't fly live (no sim access in the room), fall back to
`python3 run_pilotai.py --analyze` against a flight file brought on a USB
drive -- steps 3-7 above are identical either way, since the Python half
doesn't know or care whether the Connector or a file on disk produced the
recording.

## 5. Status

**COMPLETE:** full Python analysis pipeline (phase detection, checklist,
mistake detection, scoring), instructor summary, concise 1-3 page PDF plus
full JSON/text reports, student/instructor name capture, auto-open +
completion banner, 30 passing tests, zero-cost local-only design.
Connector is configured for the confirmed UFly environment (P3D
4.5.13.32097, `x64`, Prepar3D v4 SDK path) and remote-SimConnect config
templates are in `Connector/config-templates/`.

**NEEDS REAL-WORLD TESTING:** C# Connector compiling against the real
SimConnect SDK on a Windows machine, an actual SimConnect connection to
Prepar3D, shutdown auto-detection against real telemetry, the automatic
Python subprocess call (including the interactive name prompts) on a real
Windows machine, remote/networked SimConnect if attempted -- none of this
development environment has Windows, `dotnet`, or the SimConnect SDK
available to compile and run it directly.

**NOT REQUIRED FOR DEMO:** the optional local-LLM summary hook,
multi-flight/touch-and-go support, any dashboard/voice (removed by
design), wind telemetry, other aircraft types.

## 6. Troubleshooting

**SimConnect cannot connect** -- confirm Prepar3D is fully loaded first;
confirm the managed DLL path in the `.csproj`; confirm the *native*
`SimConnect.dll` sits next to the built `.exe`.

**Remote connection fails** -- `ping` the sim PC's IP first, before
touching SimConnect at all. Confirm both machines are on the same subnet.
Ask specifically about Wi-Fi client/AP isolation.

**Firewall blocks communication** -- check Windows Defender Firewall's
"allow an app" list for Prepar3D on the sim PC.

**Connector fails to compile** -- confirm `dotnet --version` and the .NET
Framework 4.8 targeting pack are present; confirm `SimConnectDllPath`
points at a real file.

**Telemetry is missing** -- check the `.csv` is actually growing; check the
console for a SimConnect exception; confirm the Cessna 172 is loaded.

**Flight does not end automatically** -- `FlightEndDetector` requires the
parking brake set and near-zero airspeed, sustained 3 seconds, after the
engine has genuinely run. Set the brake.

**PDF is not generated** -- check `Data/logs/pilotai.log` for a Python
traceback; confirm `python` (not `python3`) is on PATH where the Connector
runs, or edit `PythonExecutable` in `Connector/Program.cs`; confirm
`reportlab` is installed in that Python environment.

**Report has incorrect scoring** -- open the sibling `.json` report and
check the `mistakes` list -- every deduction is fully explained with its
threshold. Thresholds were tuned against synthetic data (documented in
`docs/ROADMAP.md`), not a logic bug.

**Console appears to hang after "Engine shutdown detected"** -- it's
almost always waiting on the `Student Pilot Name:` / `Instructor/Supervisor
Name:` prompts; look at the console, not a log file, and type the names.
If you genuinely want to skip this (e.g. an unattended run), use
`python3 run_pilotai.py --student-name "..." --instructor-name "..."`
directly instead of relying on the Connector's automatic call.

**PDF doesn't open automatically** -- auto-open is best-effort
(`Data/logs/pilotai.log` will show why it failed, e.g. no default PDF
viewer registered); the PDF still exists at the path printed in the
completion banner -- open it manually, or run with `--no-open` to stop
expecting it.

## 7. Final answer

1. **Ready for a UFly demo?** The analysis/report half: yes, confidently.
   The SimConnect half: built, not yet proven. Let the proven half carry
   the demo.
2. **First thing to test:** `python3 run_pilotai.py --test` on your Mac,
   right now, before anything else.
3. **Biggest risk:** the C# Connector has never been compiled or run
   against a real SimConnect SDK or a real Prepar3D session.
4. **Backup plan:** show a pre-generated sample PDF, and if time allows,
   run `python3 run_pilotai.py --analyze` live against a flight file
   brought on a USB drive -- still a fully real demonstration of the
   harder, more valuable half of the system.
