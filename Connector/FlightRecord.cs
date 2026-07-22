using System;
using System.Globalization;

namespace PilotAI.Connector
{
    /// <summary>
    /// One sample of Cessna 172 flight data. Field names mirror the JSON
    /// schema the Python side expects (see Engine/telemetry_schema.py) --
    /// keep both sides in sync if either one changes, since the recorded
    /// file (TelemetryRecorder) is the only contract between them.
    /// </summary>
    public class FlightRecord
    {
        public DateTime Timestamp;
        public double ElapsedSeconds;
        public double AltitudeFt;
        public double AirspeedKt;
        public double VerticalSpeedFpm;
        public double HeadingDeg;
        public double PitchDeg;
        public double BankDeg;
        public double LatitudeDeg;
        public double LongitudeDeg;
        public double ThrottlePct;
        public double FlapsPct;
        public bool GearDown;
        public double Rpm;
        public double FuelQtyGal;
        public bool ParkingBrake;
        public bool EngineCombustion;
        public bool AutopilotMaster;
        public double SimTimeSeconds;

        public static string[] CsvHeader => new[]
        {
            "time", "elapsed_sec", "altitude_ft", "airspeed_kt", "vertical_speed_fpm",
            "heading_deg", "pitch_deg", "bank_deg", "latitude_deg", "longitude_deg",
            "throttle_pct", "flaps_pct", "gear_down", "rpm", "fuel_qty_gal",
            "parking_brake", "engine_combustion", "autopilot_master", "sim_time_sec",
        };

        public string ToCsvRow()
        {
            var c = CultureInfo.InvariantCulture;
            return string.Join(",", new[]
            {
                Timestamp.ToString("HH:mm:ss", c),
                ElapsedSeconds.ToString(c),
                AltitudeFt.ToString(c),
                AirspeedKt.ToString(c),
                VerticalSpeedFpm.ToString(c),
                HeadingDeg.ToString(c),
                PitchDeg.ToString(c),
                BankDeg.ToString(c),
                LatitudeDeg.ToString(c),
                LongitudeDeg.ToString(c),
                ThrottlePct.ToString(c),
                FlapsPct.ToString(c),
                GearDown ? "true" : "false",
                Rpm.ToString(c),
                FuelQtyGal.ToString(c),
                ParkingBrake ? "true" : "false",
                EngineCombustion ? "true" : "false",
                AutopilotMaster ? "true" : "false",
                SimTimeSeconds.ToString(c),
            });
        }

        /// <summary>
        /// Hand-rolled JSON, deliberately with no external library dependency
        /// -- this needs to build on a sim PC that might not have NuGet
        /// package restore available on demo day. Every field here is a
        /// plain number, string, or bool, so there's no escaping to worry
        /// about beyond the fixed-format time string.
        /// </summary>
        public string ToJson()
        {
            var c = CultureInfo.InvariantCulture;
            return "{"
                + $"\"time\":\"{Timestamp:HH:mm:ss}\","
                + $"\"elapsed_sec\":{ElapsedSeconds.ToString(c)},"
                + $"\"altitude_ft\":{AltitudeFt.ToString(c)},"
                + $"\"airspeed_kt\":{AirspeedKt.ToString(c)},"
                + $"\"vertical_speed_fpm\":{VerticalSpeedFpm.ToString(c)},"
                + $"\"heading_deg\":{HeadingDeg.ToString(c)},"
                + $"\"pitch_deg\":{PitchDeg.ToString(c)},"
                + $"\"bank_deg\":{BankDeg.ToString(c)},"
                + $"\"latitude_deg\":{LatitudeDeg.ToString(c)},"
                + $"\"longitude_deg\":{LongitudeDeg.ToString(c)},"
                + $"\"throttle_pct\":{ThrottlePct.ToString(c)},"
                + $"\"flaps_pct\":{FlapsPct.ToString(c)},"
                + $"\"gear_down\":{(GearDown ? "true" : "false")},"
                + $"\"rpm\":{Rpm.ToString(c)},"
                + $"\"fuel_qty_gal\":{FuelQtyGal.ToString(c)},"
                + $"\"parking_brake\":{(ParkingBrake ? "true" : "false")},"
                + $"\"engine_combustion\":{(EngineCombustion ? "true" : "false")},"
                + $"\"autopilot_master\":{(AutopilotMaster ? "true" : "false")},"
                + $"\"sim_time_sec\":{SimTimeSeconds.ToString(c)}"
                + "}";
        }
    }
}
