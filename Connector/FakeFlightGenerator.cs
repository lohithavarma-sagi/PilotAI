using System;
using System.Threading;

namespace PilotAI.Connector
{
    /// <summary>
    /// Produces a synthetic Cessna 172 flight in real time, so the
    /// Connector's recording pipeline can be demoed even when the simulator
    /// isn't running or SimConnect refuses to connect (test mode).
    ///
    /// Mirrors the same phase structure and numbers as the canonical
    /// generator, Engine/synthetic_flight.py: engine start, taxi, takeoff
    /// roll, rotation, climb, cruise (with one brief steep-bank excursion),
    /// descent, a slightly fast/steep final approach, a firm touchdown,
    /// taxi in, and shutdown -- so a test-mode report looks the same
    /// regardless of which half of PilotAI produced the data. If you change
    /// one, change the other.
    /// </summary>
    public class FakeFlightGenerator
    {
        private const double StartLatDeg = 43.6777;
        private const double StartLonDeg = -79.6248;
        private const double FieldElevationFt = 650.0;
        private const double CruiseAltitudeFt = 3500.0;
        private const double CruiseAirspeedKt = 112.0;
        private const double CruiseHeadingDeg = 270.0;
        private const double SimTimeStartSec = 14 * 3600; // 14:00:00Z

        private readonly Random _rnd = new Random(42);

        private static (double, double) AdvancePosition(double latDeg, double lonDeg, double headingDeg, double groundSpeedKt, double dtSec)
        {
            double distanceNm = (groundSpeedKt / 3600.0) * dtSec;
            double headingRad = headingDeg * Math.PI / 180.0;
            double deltaLat = (distanceNm / 60.0) * Math.Cos(headingRad);
            double deltaLon = (distanceNm / 60.0) * Math.Sin(headingRad) / Math.Max(Math.Cos(latDeg * Math.PI / 180.0), 0.1);
            return (latDeg + deltaLat, lonDeg + deltaLon);
        }

        /// <summary>
        /// Calls onSample once per sample for the whole synthetic flight,
        /// paced in real time to match sampleIntervalSeconds. stopRequested
        /// is checked between samples so a live demo can be cut short
        /// cleanly (e.g. from a Ctrl+C handler).
        /// </summary>
        public void Run(Action<FlightRecord> onSample, Func<bool> stopRequested, double sampleIntervalSeconds = 0.5, bool realTime = true)
        {
            double elapsed = 0;
            double lat = StartLatDeg, lon = StartLonDeg;
            double heading = CruiseHeadingDeg;
            double fuel = 40.0; // gallons, roughly a C172's usable fuel load
            double fuelBurnPerSec = 10.0 / 3600.0; // ~10 GPH cruise burn
            double simTime = SimTimeStartSec;
            var startTime = DateTime.Now;

            void Emit(double altitude, double airspeed, double vs, double hdg, double pitch, double bank,
                      double throttle, double flaps, bool gearDown, double rpm, bool parkingBrake,
                      bool engineOn, bool autopilot, bool jitter = true)
            {
                double alt = altitude;
                double speed = Math.Max(airspeed, 0.0);
                double hd = hdg;
                if (jitter)
                {
                    alt += _rnd.NextDouble() * 10 - 5;
                    speed += _rnd.NextDouble() * 2 - 1;
                    hd += _rnd.NextDouble() - 0.5;
                }
                (lat, lon) = AdvancePosition(lat, lon, hd, speed, sampleIntervalSeconds);

                var record = new FlightRecord
                {
                    Timestamp = startTime.AddSeconds(elapsed),
                    ElapsedSeconds = Math.Round(elapsed, 2),
                    AltitudeFt = Math.Round(alt, 1),
                    AirspeedKt = Math.Round(speed, 1),
                    VerticalSpeedFpm = Math.Round(vs, 1),
                    HeadingDeg = Math.Round(((hd % 360) + 360) % 360, 1),
                    PitchDeg = Math.Round(pitch, 1),
                    BankDeg = Math.Round(bank, 1),
                    LatitudeDeg = Math.Round(lat, 6),
                    LongitudeDeg = Math.Round(lon, 6),
                    ThrottlePct = Math.Round(Math.Max(0, Math.Min(100, throttle)), 1),
                    FlapsPct = Math.Round(Math.Max(0, Math.Min(100, flaps)), 1),
                    GearDown = gearDown,
                    Rpm = Math.Round(rpm, 0),
                    FuelQtyGal = Math.Round(Math.Max(fuel, 0.0), 2),
                    ParkingBrake = parkingBrake,
                    EngineCombustion = engineOn,
                    AutopilotMaster = autopilot,
                    SimTimeSeconds = Math.Round(simTime, 1),
                };
                onSample(record);
                elapsed += sampleIntervalSeconds;
                simTime += sampleIntervalSeconds;
                fuel -= fuelBurnPerSec * sampleIntervalSeconds;
                if (realTime) Thread.Sleep((int)(sampleIntervalSeconds * 1000));
            }

            int NSamples(double durationSec) => Math.Max(1, (int)Math.Round(durationSec / sampleIntervalSeconds));

            // --- Flight Start: engine start, parked, brake set ---
            int n = NSamples(5);
            for (int i = 0; i < n && !stopRequested(); i++)
            {
                bool engineOn = i >= n / 3;
                Emit(FieldElevationFt, 0, 0, CruiseHeadingDeg, 0, 0, 0, 0, true, engineOn ? 800 : 0, true, engineOn, false, jitter: false);
            }

            // --- Taxi: brake released, slow roll to the runway ---
            n = NSamples(30);
            for (int i = 0; i < n && !stopRequested(); i++)
            {
                double progress = i / Math.Max(n - 1, 1.0);
                Emit(FieldElevationFt, 12 + _rnd.NextDouble() * 4 - 2, 0, CruiseHeadingDeg + progress * 20, 0, 0, 25, 0, true, 1000, false, true, false);
            }

            // --- Takeoff Roll ---
            n = NSamples(15);
            for (int i = 0; i < n && !stopRequested(); i++)
            {
                double progress = i / Math.Max(n - 1, 1.0);
                double speed = 60.0 * progress;
                double throttle = 40 + 60 * progress;
                double rpm = 1000 + 1300 * progress;
                Emit(FieldElevationFt, speed, 0, CruiseHeadingDeg, 0, 0, throttle, 10, true, rpm, false, true, false);
            }

            // --- Rotation ---
            n = NSamples(3);
            for (int i = 0; i < n && !stopRequested(); i++)
            {
                double progress = i / Math.Max(n - 1, 1.0);
                Emit(FieldElevationFt + 15 * progress, 58, 300 * progress, CruiseHeadingDeg, 7, 0, 95, 10, true, 2400, false, true, false);
            }

            // --- Climb ---
            n = NSamples(60);
            for (int i = 0; i < n && !stopRequested(); i++)
            {
                double progress = i / Math.Max(n - 1, 1.0);
                double alt = FieldElevationFt + (CruiseAltitudeFt - FieldElevationFt) * progress;
                double vs = 650 * (1 - progress * 0.3);
                double flaps = Math.Max(0.0, 10 - progress * 20);
                Emit(alt, 78 + _rnd.NextDouble() * 4 - 2, vs, CruiseHeadingDeg + progress * 3, 9 - 2 * progress, 0, 92, flaps, true, 2500, false, true, false);
            }

            // --- Cruise, with one brief steep-bank excursion; autopilot engaged partway ---
            n = NSamples(180);
            int excursionStart = (int)(n * 0.39);
            int excursionLen = Math.Max(1, NSamples(4));
            int autopilotFrom = (int)(n * 0.5);
            for (int i = 0; i < n && !stopRequested(); i++)
            {
                double bank;
                if (i >= excursionStart && i < excursionStart + excursionLen)
                {
                    double turnProgress = (double)(i - excursionStart) / excursionLen;
                    bank = 34 * Math.Sin(turnProgress * Math.PI);
                    heading += bank * 0.02;
                }
                else
                {
                    bank = _rnd.NextDouble() * 4 - 2;
                }
                bool autopilot = i >= autopilotFrom;
                Emit(CruiseAltitudeFt, CruiseAirspeedKt, _rnd.NextDouble() * 80 - 40, heading, 2.5, bank, 68, 0, true, 2350, false, true, autopilot);
            }

            // --- Descent ---
            n = NSamples(90);
            for (int i = 0; i < n && !stopRequested(); i++)
            {
                double progress = i / Math.Max(n - 1, 1.0);
                double alt = CruiseAltitudeFt - (CruiseAltitudeFt - (FieldElevationFt + 800)) * progress;
                double speed = CruiseAirspeedKt - 15 * progress;
                bool autopilot = progress < 0.6;
                Emit(alt, speed, -550, CruiseHeadingDeg, -1.5, _rnd.NextDouble() * 6 - 3, 45, 0, true, 2100, false, true, autopilot);
            }

            // --- Final approach: intentionally a bit fast and steep ---
            n = NSamples(60);
            for (int i = 0; i < n && !stopRequested(); i++)
            {
                double progress = i / Math.Max(n - 1, 1.0);
                double alt = (FieldElevationFt + 800) - 750 * progress;
                double speed = 78 - 4 * progress;
                double flaps = 10 + 20 * progress;
                double vs = -760 + 20 * progress;
                Emit(alt, speed, vs, CruiseHeadingDeg, -2 + 3 * progress, _rnd.NextDouble() * 4 - 2, 35, flaps, true, 1900, false, true, false);
            }

            // --- Flare & touchdown: stays hard on purpose ---
            n = NSamples(7);
            for (int i = 0; i < n && !stopRequested(); i++)
            {
                double progress = i / Math.Max(n - 1, 1.0);
                double alt = FieldElevationFt + 50 * (1 - progress);
                double speed = 72 - 6 * progress;
                double vs = -340 + 10 * progress;
                Emit(alt, speed, vs, CruiseHeadingDeg, 4 + 4 * progress, 0, 20, 30, true, 1500, false, true, false, jitter: false);
            }

            // --- Landing rollout: decelerate from touchdown speed to taxi speed ---
            n = NSamples(10);
            for (int i = 0; i < n && !stopRequested(); i++)
            {
                double progress = i / Math.Max(n - 1, 1.0);
                double speed = Math.Max(30, 66 - 36 * progress);
                Emit(FieldElevationFt, speed, 0, CruiseHeadingDeg, 0, 0, 0, 30, true, 1000, false, true, false);
            }

            // --- Taxi In ---
            n = NSamples(20);
            for (int i = 0; i < n && !stopRequested(); i++)
            {
                double progress = i / Math.Max(n - 1, 1.0);
                double speed = Math.Max(0.0, 15 * (1 - progress));
                bool brake = progress >= 0.97;
                Emit(FieldElevationFt, speed, 0, CruiseHeadingDeg - progress * 15, 0, 0, 15, 0, true, 900, brake, true, false);
            }

            // --- Shutdown ---
            n = NSamples(5);
            for (int i = 0; i < n && !stopRequested(); i++)
            {
                double progress = i / Math.Max(n - 1, 1.0);
                bool engineOn = progress < 0.4;
                double rpm = engineOn ? 900 * (1 - progress) : 0;
                Emit(FieldElevationFt, 0, 0, CruiseHeadingDeg, 0, 0, 0, 0, true, rpm, true, engineOn, false, jitter: false);
            }
        }
    }
}
