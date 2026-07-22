using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace PilotAI.Connector
{
    /// <summary>
    /// Buffers FlightRecord samples during a flight and writes them out as
    /// both CSV and JSON into Data/flights/. Purely local disk I/O -- no
    /// networking, by design (see docs/ARCHITECTURE.md).
    ///
    /// CSV is written one line at a time as samples arrive, so a crash
    /// mid-flight still leaves a usable partial file -- useful insurance for
    /// a live demo. JSON is a single array, which can only be closed off
    /// validly once recording stops, so it's written from the in-memory
    /// buffer in Stop(). run_pilotai.py can read either format.
    /// </summary>
    public class TelemetryRecorder : IDisposable
    {
        private readonly List<FlightRecord> _records = new List<FlightRecord>();
        private StreamWriter _csvWriter;

        public IReadOnlyList<FlightRecord> Records => _records;
        public string CsvPath { get; }
        public string JsonPath { get; }

        public TelemetryRecorder(string dataDir, string sessionName = null)
        {
            Directory.CreateDirectory(dataDir);
            var stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
            var name = string.IsNullOrWhiteSpace(sessionName) ? $"flight_{stamp}" : sessionName;
            CsvPath = Path.Combine(dataDir, name + ".csv");
            JsonPath = Path.Combine(dataDir, name + ".json");
        }

        public void Start()
        {
            _csvWriter = new StreamWriter(CsvPath, false, Encoding.UTF8);
            _csvWriter.WriteLine(string.Join(",", FlightRecord.CsvHeader));
            _csvWriter.Flush();
        }

        /// <summary>Call this once per sample -- wire it directly to SimConnectReader.FlightDataReceived (or FakeFlightGenerator's callback in test mode).</summary>
        public void RecordSample(FlightRecord record)
        {
            _records.Add(record);
            _csvWriter?.WriteLine(record.ToCsvRow());
            _csvWriter?.Flush();
        }

        /// <summary>Finalizes the JSON file from everything recorded so far. Call once, at the end of a flight.</summary>
        public void Stop()
        {
            _csvWriter?.Flush();
            _csvWriter?.Dispose();
            _csvWriter = null;

            var sb = new StringBuilder();
            sb.Append("[\n");
            for (int i = 0; i < _records.Count; i++)
            {
                sb.Append("  ").Append(_records[i].ToJson());
                sb.Append(i < _records.Count - 1 ? ",\n" : "\n");
            }
            sb.Append("]\n");
            File.WriteAllText(JsonPath, sb.ToString(), Encoding.UTF8);
        }

        public void Dispose()
        {
            _csvWriter?.Dispose();
        }
    }
}
