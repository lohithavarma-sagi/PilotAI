using System;

namespace PilotAI.Connector
{
    /// <summary>
    /// Decides "the flight is over" from telemetry alone, so the Connector
    /// can automatically stop recording and kick off analysis with no
    /// manual interaction -- no separate "stop recording" button, no
    /// second command to run afterward.
    ///
    /// A flight is over once the engine has genuinely been running at some
    /// point (so a fresh, still-parked session doesn't trigger immediately --
    /// engine off + parking brake set + stationary is also the *starting*
    /// state) and then engine combustion stops with the parking brake set
    /// and the aircraft stationary, sustained for a few seconds so a single
    /// noisy sample can't end the recording early.
    /// </summary>
    public class FlightEndDetector
    {
        private const double SustainedSeconds = 3.0;

        private bool _engineHasRunThisFlight;
        private double? _shutdownConditionStartElapsedSec;

        /// <summary>Feed it every sample. Returns true the moment the flight is confirmed over.</summary>
        public bool Update(FlightRecord record)
        {
            if (record.EngineCombustion)
            {
                _engineHasRunThisFlight = true;
                _shutdownConditionStartElapsedSec = null;
                return false;
            }

            if (!_engineHasRunThisFlight)
                return false; // engine never started yet -- this is the pre-flight parked state, not a shutdown

            bool looksShutDown = record.ParkingBrake && record.AirspeedKt < 1.0;
            if (!looksShutDown)
            {
                _shutdownConditionStartElapsedSec = null;
                return false;
            }

            if (_shutdownConditionStartElapsedSec is null)
            {
                _shutdownConditionStartElapsedSec = record.ElapsedSeconds;
                return false;
            }

            return record.ElapsedSeconds - _shutdownConditionStartElapsedSec.Value >= SustainedSeconds;
        }

        /// <summary>Call when starting a new recording session so a leftover detector doesn't end it immediately.</summary>
        public void Reset()
        {
            _engineHasRunThisFlight = false;
            _shutdownConditionStartElapsedSec = null;
        }
    }
}
