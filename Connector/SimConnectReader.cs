using System;
using System.Runtime.InteropServices;
using System.Threading;
using Microsoft.FlightSimulator.SimConnect;

namespace PilotAI.Connector
{
    /// <summary>
    /// Wraps the SimConnect managed API and turns Prepar3D/MSFS's Cessna 172
    /// simulation variables into FlightRecord events, at a configurable
    /// sample rate (default 0.5s, per PilotAI's telemetry stream spec).
    ///
    /// This is a console app, not a WinForms/WPF app, so there's no window
    /// message pump available for SimConnect's usual WM_USER callback style.
    /// Instead we give SimConnect a wait handle and poll it from a background
    /// thread -- the standard approach for console-hosted SimConnect clients.
    ///
    /// SimConnect's period enum only offers discrete choices (per-sim-frame,
    /// per-second, ...) with no direct "every 0.25s" option, and per-sim-frame
    /// rate varies with the sim's actual frame rate. So this requests data
    /// every sim frame and self-throttles in code to the requested interval --
    /// robust regardless of frame rate, and supports any interval PilotAI's
    /// settings allow (0.25s-1s).
    /// </summary>
    public class SimConnectReader : IDisposable
    {
        private const string AppName = "PilotAI Connector";

        private enum Definitions
        {
            FlightData,
        }

        private enum Requests
        {
            FlightData,
        }

        // Field order here must exactly match the order of AddToDataDefinition
        // calls in RegisterFlightDataDefinition -- SimConnect marshals the
        // response into this struct positionally, not by name.
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 1)]
        private struct RawFlightData
        {
            public double Altitude;
            public double Airspeed;
            public double VerticalSpeed;
            public double Heading;
            public double Pitch;
            public double Bank;
            public double Latitude;
            public double Longitude;
            public double Throttle;
            public double Flaps;
            public double GearPosition;
            public double Rpm;
            public double Fuel;
            public double ParkingBrake;
            public double EngineCombustion;
            public double AutopilotMaster;
            public double ZuluTime;
        }

        private readonly double _sampleIntervalSeconds;
        private SimConnect _simConnect;
        private readonly AutoResetEvent _simConnectEvent = new AutoResetEvent(false);
        private Thread _messagePumpThread;
        private volatile bool _running;
        private DateTime _startTime;
        private DateTime _lastEmit = DateTime.MinValue;

        /// <summary>Raised at the configured sample rate with the latest flight data, once connected.</summary>
        public event Action<FlightRecord> FlightDataReceived;

        /// <summary>Raised if the simulator closes or SimConnect otherwise drops the connection.</summary>
        public event Action Disconnected;

        public SimConnectReader(double sampleIntervalSeconds = 0.5)
        {
            _sampleIntervalSeconds = sampleIntervalSeconds;
        }

        /// <summary>
        /// Attempts to connect to a running Prepar3D/MSFS instance. Returns
        /// false (rather than throwing) if the sim isn't running -- Program.cs
        /// uses that to retry (auto-reconnect) or fall back to
        /// FakeFlightGenerator for test mode.
        /// </summary>
        public bool Connect()
        {
            try
            {
                _simConnect = new SimConnect(AppName, IntPtr.Zero, 0, _simConnectEvent, 0);
            }
            catch (COMException)
            {
                _simConnect = null;
                return false;
            }

            RegisterFlightDataDefinition();

            _simConnect.OnRecvSimobjectDataBytype += OnRecvSimobjectDataBytype;
            _simConnect.OnRecvQuit += (sender, data) =>
            {
                _running = false;
                Disconnected?.Invoke();
            };
            _simConnect.OnRecvException += (sender, data) =>
                Console.Error.WriteLine("SimConnect exception: " + (SIMCONNECT_EXCEPTION)data.dwException);

            // Every sim frame, self-throttled to _sampleIntervalSeconds in
            // OnRecvSimobjectDataBytype -- see the class-level comment for why.
            _simConnect.RequestDataOnSimObject(
                Requests.FlightData,
                Definitions.FlightData,
                SimConnect.SIMCONNECT_OBJECT_ID_USER,
                SIMCONNECT_PERIOD.SIM_FRAME,
                SIMCONNECT_DATA_REQUEST_FLAG.DEFAULT,
                0, 0, 0);

            _startTime = DateTime.Now;
            _lastEmit = DateTime.MinValue;
            _running = true;
            _messagePumpThread = new Thread(MessagePumpLoop) { IsBackground = true };
            _messagePumpThread.Start();
            return true;
        }

        private void RegisterFlightDataDefinition()
        {
            void Add(string simVarName, string unit) =>
                _simConnect.AddToDataDefinition(
                    Definitions.FlightData, simVarName, unit,
                    SIMCONNECT_DATATYPE.FLOAT64, 0.0f, SimConnect.SIMCONNECT_UNUSED);

            Add("INDICATED ALTITUDE", "feet");
            Add("AIRSPEED INDICATED", "knots");
            Add("VERTICAL SPEED", "feet per minute");
            Add("PLANE HEADING DEGREES MAGNETIC", "degrees");
            Add("PLANE PITCH DEGREES", "degrees");
            Add("PLANE BANK DEGREES", "degrees");
            Add("PLANE LATITUDE", "degrees");
            Add("PLANE LONGITUDE", "degrees");
            Add("GENERAL ENG THROTTLE LEVER POSITION:1", "percent");
            Add("FLAPS HANDLE PERCENT", "percent");
            // The Cessna 172 has fixed (non-retractable) gear, so this will
            // always read "down" for a C172 -- it's still wired up so this
            // connector also works unmodified on retractable-gear aircraft.
            Add("GEAR HANDLE POSITION", "percent");
            Add("GENERAL ENG RPM:1", "rpm");
            Add("FUEL TOTAL QUANTITY", "gallons");
            Add("BRAKE PARKING POSITION", "position");
            Add("GENERAL ENG COMBUSTION:1", "bool");
            Add("AUTOPILOT MASTER", "bool");
            Add("ZULU TIME", "seconds");

            _simConnect.RegisterDataDefineStruct<RawFlightData>(Definitions.FlightData);
        }

        private void MessagePumpLoop()
        {
            while (_running)
            {
                // A 1-second timeout means Stop() is never blocked waiting
                // indefinitely, even if the sim stops sending messages.
                if (_simConnectEvent.WaitOne(1000))
                {
                    try
                    {
                        _simConnect?.ReceiveMessage();
                    }
                    catch (COMException)
                    {
                        _running = false;
                        Disconnected?.Invoke();
                    }
                }
            }
        }

        private void OnRecvSimobjectDataBytype(SimConnect sender, SIMCONNECT_RECV_SIMOBJECT_DATA_BYTYPE data)
        {
            var now = DateTime.Now;
            if ((now - _lastEmit).TotalSeconds < _sampleIntervalSeconds)
                return;
            _lastEmit = now;

            var raw = (RawFlightData)data.dwData[0];

            var record = new FlightRecord
            {
                Timestamp = now,
                ElapsedSeconds = Math.Round((now - _startTime).TotalSeconds, 2),
                AltitudeFt = raw.Altitude,
                AirspeedKt = raw.Airspeed,
                VerticalSpeedFpm = raw.VerticalSpeed,
                HeadingDeg = raw.Heading,
                // SimConnect's PLANE PITCH DEGREES is positive nose-down;
                // PilotAI (and the Python Engine) uses the pilot's usual
                // convention where positive pitch means nose up.
                PitchDeg = -raw.Pitch,
                BankDeg = raw.Bank,
                LatitudeDeg = raw.Latitude,
                LongitudeDeg = raw.Longitude,
                ThrottlePct = raw.Throttle,
                FlapsPct = raw.Flaps,
                GearDown = raw.GearPosition > 50.0,
                Rpm = raw.Rpm,
                FuelQtyGal = raw.Fuel,
                ParkingBrake = raw.ParkingBrake > 0.5,
                EngineCombustion = raw.EngineCombustion > 0.5,
                AutopilotMaster = raw.AutopilotMaster > 0.5,
                SimTimeSeconds = raw.ZuluTime,
            };

            FlightDataReceived?.Invoke(record);
        }

        public void Stop()
        {
            _running = false;
            _messagePumpThread?.Join(2000);
        }

        public void Dispose()
        {
            Stop();
            _simConnect?.Dispose();
            _simConnectEvent.Dispose();
        }
    }
}
