# C# Connector — Deployment Checklist for a Real Prepar3D Test

This is the narrow, Connector-specific companion to `docs/UFLY_DEMO_GUIDE.md`
(which covers the whole demo, including the optional remote-networking
setup). Read this one first if all you're trying to do is get the
Connector talking to a real Prepar3D session for the first time.

**Confirmed target:** Prepar3D 4.5.13.32097 / SimConnect 4.5.0.0.
`PilotAI.Connector.csproj` is already configured for it (`x64` platform,
`SimConnectDllPath` defaulting to the Prepar3D v4 SDK location) -- the
32-bit/64-bit risk noted further down used to be a "watch out for this"
item and is now a fix already applied in the `.csproj`.

## Dependency footprint (verified by inspection, not assumed)

Every `.cs` file's `using` statements were checked directly. The only
external dependency anywhere in `Connector/` is the single SimConnect
reference in the `.csproj` -- no NuGet packages, hand-written JSON/CSV.
That's deliberately minimal; there is very little here that can fail
besides SimConnect itself.

## Requirements

| What | Needed | Why |
|---|---|---|
| Windows | Whatever P3D itself needs (Win 10/11 64-bit) | No extra OS requirement from the Connector |
| .NET SDK 6+ | On the **build** machine only | To compile (`dotnet build`) |
| .NET Framework 4.8 runtime | On the **run** machine | The `.csproj` targets `net48`; almost certainly already present on any current Windows 10/11 install |
| `Microsoft.FlightSimulator.SimConnect.dll` (managed) | Build time | From the SimConnect SDK (`SimConnect SDK\lib\managed\`); auto-copied to the output folder by `dotnet build` because of `<Private>true</Private>` in the `.csproj` |
| `SimConnect.dll` (native) | Run time | From the same SDK (`SimConnect SDK\lib\`, *not* `lib\managed\`) -- check Prepar3D's own install folder first, it's very likely already there since P3D itself depends on it. **Not** copied automatically; you must place it next to the built `.exe` yourself. |

## Deployment structure

`Program.cs` computes its data/report paths relative to its own build
location:
```csharp
string repoRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
```
That walks up from `Connector/bin/Debug/net48/` back to the project root,
where it expects to find `run_pilotai.py` and writes `Data/flights/`. So:
**copy/clone the whole project onto the Windows machine and build/run the
Connector in its normal location** -- don't extract just the `.exe` and
DLLs into an isolated folder, or the automatic Python hand-off will fail
to find `run_pilotai.py` (it fails gracefully with a manual-run message,
it won't crash, but you'll lose the "no manual steps" behavior).

```
PilotAI/
  Connector/
    bin/Debug/net48/
      PilotAI.Connector.exe
      PilotAI.Connector.dll
      Microsoft.FlightSimulator.SimConnect.dll   <- copied automatically
      SimConnect.dll                              <- copy this one yourself
    PilotAI.Connector.csproj
    *.cs
  run_pilotai.py
  Engine/, Reports/, requirements.txt           <- only needed if Python also runs here
  Data/flights/                                  <- created automatically
```

If Python won't be on the same Windows machine, `Engine/`/`Reports/`
aren't required there -- the Connector's auto-launch of Python will fail
gracefully, leaving the `.json`/`.csv` recording for you to copy to the
Mac and analyze with `python3 run_pilotai.py --analyze` by hand.

## Where it can run

| Where | Works | Setup |
|---|---|---|
| Directly on the UFly sim PC | Yes -- the default/simplest path | Just the two DLLs above |
| Another Windows laptop, same LAN | Yes, via remote SimConnect | Copy `Connector/config-templates/SimConnect.xml.template` (sim PC) + `SimConnect.cfg.template` (laptop), fill in the real IP -- see `docs/UFLY_DEMO_GUIDE.md` |

**Recommendation for a first real-world test: run directly on the UFly PC.**
Zero network variables. Save remote SimConnect for once same-machine works.

## Test order for tomorrow

1. **Build.** `dotnet build -p:SimConnectDllPath="<path>"` in `Connector/`.
   Rules out the single biggest unknown (never compiled before).
2. **DLL loads.** Copy the native `SimConnect.dll` next to the built
   `.exe`, run it *without* P3D open. Expect the TEST MODE fallback
   message. A crash instead usually means a 32-bit/64-bit mismatch (see
   Troubleshooting).
3. **Connects.** Load the Cessna 172 in P3D first, then run the Connector.
   Expect `"Connected to the simulator..."`.
4. **Real telemetry.** Let it run 15-20s, open the growing `.csv`, confirm
   altitude/airspeed are real, changing numbers.
5. **Shutdown detection.** Fly briefly, set the parking brake, shut the
   engine down, wait ~3s. Expect `"Engine shutdown detected..."`.
6. **Python hand-off** (only if Python is on the same machine). Expect
   `"Report generated successfully."` and a PDF in `Data/flights/`.

## Troubleshooting note not to be caught off guard by

`.csproj` now pins `<PlatformTarget>x64</PlatformTarget>` explicitly
(Prepar3D v4's SimConnect DLLs are 64-bit only) -- this used to be an
AnyCPU risk to watch for and has been fixed proactively now that UFly's
exact environment (P3D 4.5.13.32097) is known. If SimConnect still fails
to load at runtime, it's most likely the *native* `SimConnect.dll` missing
next to the built `.exe` (step 2 below), not an architecture mismatch.
