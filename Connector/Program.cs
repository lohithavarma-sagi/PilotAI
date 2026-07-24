using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

namespace PilotAI.Connector
{
    /// <summary>
    /// Entry point for the PilotAI Connector. Connects to Prepar3D/MSFS via
    /// SimConnect and records telemetry locally -- no networking, no
    /// dashboard (see docs/ARCHITECTURE.md for why PilotAI moved to a fully
    /// local, record-then-analyze workflow). Recording starts the moment
    /// SimConnect connects and ends automatically once the engine has been
    /// shut down (FlightEndDetector), at which point this process
    /// automatically runs `python run_pilotai.py --analyze` on the
    /// recording -- from a student's point of view, they fly, shut the
    /// engine down, and the PDF is just there.
    ///
    /// If the simulator isn't running (or SimConnect refuses the
    /// connection), automatically falls back to a synthetic test flight so
    /// the whole pipeline can still be demoed. If the simulator closes
    /// mid-session, automatically retries the SimConnect connection.
    /// </summary>
    public static class Program
    {
        private const double SampleIntervalSeconds = 0.5;
        private static readonly TimeSpan ReconnectDelay = TimeSpan.FromSeconds(5);
        private const int MinimumSamplesToAnalyze = 10;

        // On Windows this is usually "python", not "python3" -- adjust if
        // your install differs (e.g. a specific venv's python.exe).
        private const string PythonExecutable = "python";

        public static void Main(string[] args)
        {
            Console.WriteLine("PilotAI Connector starting...");

            string repoRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));
            string dataDir = Path.Combine(repoRoot, "Data", "flights");

            var stopSignal = new ManualResetEvent(false);
            Console.CancelKeyPress += (sender, eventArgs) =>
            {
                eventArgs.Cancel = true;
                stopSignal.Set();
            };

            while (!stopSignal.WaitOne(0))
            {
                RunOneFlightSession(repoRoot, dataDir, stopSignal);

                if (!stopSignal.WaitOne(0))
                {
                    Console.WriteLine("Ready for the next flight (Ctrl+C to quit)...");
                    stopSignal.WaitOne(ReconnectDelay);
                }
            }

            Console.WriteLine("PilotAI Connector stopped.");
        }

        /// <summary>
        /// Records exactly one flight: connect (or fall back to test mode),
        /// record until the engine is shut down, Ctrl+C, or the simulator
        /// disconnects, then finalize the recording and analyze it.
        /// </summary>
        private static void RunOneFlightSession(string repoRoot, string dataDir, ManualResetEvent stopSignal)
        {
            var recorder = new TelemetryRecorder(dataDir);
            recorder.Start();
            var endDetector = new FlightEndDetector();
            var flightEnded = new ManualResetEvent(false);

            void OnSample(FlightRecord record)
            {
                recorder.RecordSample(record);
                if (endDetector.Update(record))
                {
                    flightEnded.Set();
                }
            }

            var reader = new SimConnectReader(SampleIntervalSeconds);
            bool connected;
            try
            {
                connected = reader.Connect();
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"Could not connect to SimConnect: {ex.Message}");
                connected = false;
            }

            if (connected)
            {
                Console.WriteLine("Connected to the simulator. Recording will start now and stop automatically after engine shutdown.");
                reader.FlightDataReceived += OnSample;

                var disconnected = new ManualResetEvent(false);
                reader.Disconnected += () =>
                {
                    Console.WriteLine("Simulator disconnected.");
                    disconnected.Set();
                };

                WaitHandle.WaitAny(new WaitHandle[] { stopSignal, disconnected, flightEnded });
                if (flightEnded.WaitOne(0))
                {
                    Console.WriteLine("Engine shutdown detected -- flight complete.");
                }
                reader.Stop();
            }
            else
            {
                Console.WriteLine("SimConnect unavailable (is the simulator running?) -- running in TEST MODE with a synthetic flight.");
                var fakeFlight = new FakeFlightGenerator();
                fakeFlight.Run(OnSample, () => stopSignal.WaitOne(0) || flightEnded.WaitOne(0), SampleIntervalSeconds);
            }

            recorder.Stop();
            reader.Dispose();

            Console.WriteLine();
            Console.WriteLine("Recording saved:");
            Console.WriteLine($"  JSON: {recorder.JsonPath}");
            Console.WriteLine($"  CSV:  {recorder.CsvPath}");
            Console.WriteLine();

            if (recorder.Records.Count < MinimumSamplesToAnalyze)
            {
                Console.WriteLine("Recording too short to analyze (nothing happened this session) -- skipping report generation.");
                return;
            }

            RunAnalysis(repoRoot, recorder.JsonPath);
        }

        /// <summary>
        /// Automatically runs the Python analysis + report pipeline on the
        /// recording that was just finished -- this is what makes "shut the
        /// engine down and the PDF is just there" true, with no second
        /// command for the student or instructor to run.
        ///
        /// stdio is inherited (not redirected), so run_pilotai.py's
        /// Student Pilot Name / Instructor Name prompts appear right in
        /// this same console and PilotAI waits for them to be typed here --
        /// that's why this blocks indefinitely instead of on a short
        /// timeout, unlike a purely unattended subprocess call.
        /// </summary>
        private static void RunAnalysis(string repoRoot, string flightJsonPath)
        {
            Console.WriteLine("Analyzing flight and generating instructor report...");
            Console.WriteLine("(You may be prompted below for the Student Pilot Name and Instructor/Supervisor Name.)");
            var psi = new ProcessStartInfo
            {
                FileName = PythonExecutable,
                WorkingDirectory = repoRoot,
                UseShellExecute = false,
                RedirectStandardOutput = false,
                RedirectStandardError = false,
            };
            psi.ArgumentList.Add("run_pilotai.py");
            psi.ArgumentList.Add("--analyze");
            psi.ArgumentList.Add(flightJsonPath);

            try
            {
                using (var process = Process.Start(psi))
                {
                    process.WaitForExit();
                    if (process.ExitCode != 0)
                    {
                        Console.Error.WriteLine($"Report generation exited with code {process.ExitCode} -- see Data/logs/pilotai.log.");
                    }
                    else
                    {
                        Console.WriteLine("Report generated successfully.");
                    }
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine(
                    $"Could not launch Python to generate the report ({ex.Message}). " +
                    $"Run it manually: python run_pilotai.py --analyze \"{flightJsonPath}\""
                );
            }
        }
    }
}
