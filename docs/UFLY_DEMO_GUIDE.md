# PilotAI @ UFly — Deployment, Test Plan, and Demo Guide

This is the offline reference for testing and presenting PilotAI at UFly.
Bring this file (or a printout) in case Wi-Fi is unreliable on-site.

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

On the **UFly PC**, e.g.
`%ProgramData%\Lockheed Martin\Prepar3D v5\SimConnect.xml`:
```xml
<?xml version="1.0" encoding="Windows-1252"?>
<SimBase.Document Type="SimConnect" version="1,0">
  <Descr>SimConnect</Descr>
  <Filename>SimConnect.xml</Filename>
  <SimConnect.Comm>
    <Descr>Comm</Descr>
    <Protocol>IPv4</Protocol>
    <Scope>global</Scope>
    <MaxClients>8</MaxClients>
    <Port>500</Port>
    <MaxRecvSize>41088</MaxRecvSize>
    <DisableNagle>False</DisableNagle>
  </SimConnect.Comm>
</SimBase.Document>
```
*(Verify exact path/schema against Lockheed Martin's official SimConnect
SDK docs for UFly's specific Prepar3D version -- this is a strong starting
template, not verified against a live install.)*

On the **Connector's machine**, `SimConnect.cfg` next to `PilotAI.Connector.exe`:
```ini
[SimConnect]
Protocol=IPv4
Address=<UFly sim PC's LAN IP>
Port=500
MaxReceiveSize=41088
DisableNagle=0
```

**No code changes needed.** `SimConnectReader.cs` already looks up config
index 0 (`new SimConnect(AppName, IntPtr.Zero, 0, _simConnectEvent, 0)`),
which reads entry `[SimConnect]` in `SimConnect.cfg` -- point that one entry
at the remote address and the same code connects remotely.

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
| 1 | Connect both machines to the same network | Both get an IP on the same subnet |
| 2 | Open Prepar3D, load the Cessna 172 | Sim running |
| 3 | Start the Connector | `"PilotAI Connector starting..."` |
| 4 | Confirm connection | `"Connected to the simulator..."` |
| 5 | Verify telemetry | `Data/flights/*.csv` growing with sensible values |
| 6 | Fly ~5 minutes | Taxi, takeoff, cruise, land |
| 7 | Shut engine down, brake set | `"Engine shutdown detected -- flight complete."` |
| 8 | Wait for analysis | `"Report generated successfully."` (seconds, not minutes) |
| 9 | Find the PDF | `Data/flights/flight_<timestamp>_report.pdf` |
| 10 | Print it | Standard print dialog |

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

## 5. Status

**COMPLETE:** full Python analysis pipeline (phase detection, checklist,
mistake detection, scoring), instructor summary, PDF/JSON/text reports,
30 passing tests, zero-cost local-only design.

**NEEDS REAL-WORLD TESTING:** C# Connector compiling against a real
SimConnect SDK, an actual SimConnect connection to Prepar3D, shutdown
auto-detection against real telemetry, the automatic Python subprocess
call on a real Windows machine, remote/networked SimConnect if attempted.

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
