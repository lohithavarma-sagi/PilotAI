"""
scoring_engine.py

Turns a completed FlightRecorder into eight category scores: Takeoff,
Climb, Cruise, Approach, Landing, Aircraft Control, Checklist Discipline,
and an Overall Score. Every point deducted comes with a plain-English
explanation and a recommendation -- a hard requirement, not a nice-to-have,
so there is no silent penalty anywhere in this file.

This module does not run its own threshold checks -- mistake_detector.py
is the single source of truth for "what went wrong and when" (each finding
carries a timestamp, category, and severity); this file just converts
severities into point deductions per category. Before this split existed,
scoring_engine.py ran its own separate checks with no per-event timestamp,
which meant the report's "Detected Mistakes" list and the score's
deductions could describe the same real-world moment in two different
words. One detection pass now, consumed by both scoring and reporting.

This is a rules engine, not a trained model: there's no flight-training
dataset to fit a model to, and a rules engine is auditable in a way that
matters when the person reading the report is a flight instructor deciding
whether to trust it.
"""

from typing import Any, Dict, List, Optional

import mistake_detector as md
from flight_recorder import FlightRecorder
from mistake_detector import Mistake, PhaseEvaluation, SEVERITY_POINTS


class CategoryScore:
    def __init__(self, name: str):
        self.name = name
        self.score = 100
        self.mistakes: List[Mistake] = []
        self.strengths: List[str] = []

    def apply(self, evaluation: PhaseEvaluation) -> None:
        self.strengths.extend(evaluation.strengths)
        for mistake in evaluation.mistakes:
            self.mistakes.append(mistake)
            self.score = max(0, self.score - SEVERITY_POINTS[mistake.severity])

    def deduct_checklist(self, points: int) -> None:
        self.score = max(0, self.score - points)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "mistakes": [m.to_dict() for m in self.mistakes],
            "strengths": self.strengths,
        }


def _score_checklist(recorder: FlightRecorder, checklist_summary: Optional[Dict[str, Any]]) -> CategoryScore:
    cat = CategoryScore("Checklist Discipline")
    if checklist_summary is None:
        cat.strengths.append("Checklist monitoring was not run for this flight.")
        return cat

    # A missed item has no natural "when it happened" timestamp -- it's
    # discovered only once the flight is over. Tagging these with the last
    # recorded sample (rather than 0.0) keeps the timeline in true
    # chronological order instead of sorting every missed item to the front,
    # before the flight even started.
    last = recorder.history[-1] if recorder.history else None
    elapsed_sec = last["elapsed_sec"] if last else 0.0
    time_str = last["time"] if last else ""

    for item in checklist_summary.get("missed", []):
        cat.deduct_checklist(5)
        cat.mistakes.append(Mistake(elapsed_sec, time_str, "Checklist", "missed_checklist_item", "minor",
                                     f'Missed checklist item: "{item}".',
                                     "Review the checklist for this phase before the next flight."))
    for item in checklist_summary.get("out_of_sequence", []):
        cat.deduct_checklist(3)
        cat.mistakes.append(Mistake(elapsed_sec, time_str, "Checklist", "out_of_sequence_item", "minor",
                                     f'Checklist item completed out of sequence: "{item}".',
                                     "Complete checklist items in the standard order for this phase."))
    if not checklist_summary.get("missed") and not checklist_summary.get("out_of_sequence"):
        cat.strengths.append("All checklist items completed, in the correct sequence.")

    return cat


def score_flight(recorder: FlightRecorder, checklist_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Score a completed flight across all eight categories."""
    takeoff = CategoryScore("Takeoff")
    takeoff.apply(md.evaluate_takeoff(recorder))

    climb = CategoryScore("Climb")
    climb.apply(md.evaluate_climb(recorder))

    cruise = CategoryScore("Cruise")
    cruise.apply(md.evaluate_cruise(recorder))

    approach = CategoryScore("Approach")
    approach.apply(md.evaluate_approach(recorder))

    landing = CategoryScore("Landing")
    landing_eval, landing_metrics = md.evaluate_landing(recorder)
    landing.apply(landing_eval)

    control = CategoryScore("Aircraft Control")
    control.apply(md.evaluate_aircraft_control(recorder))

    checklist = _score_checklist(recorder, checklist_summary)

    categories = [takeoff, climb, cruise, approach, landing, control, checklist]
    overall_score = round(sum(c.score for c in categories) / len(categories))

    all_mistakes = sorted(
        (m for c in categories for m in c.mistakes),
        key=lambda m: m.elapsed_sec,
    )

    return {
        "aircraft": "Cessna 172",
        "overall_score": overall_score,
        "categories": {c.name: c.to_dict() for c in categories},
        "mistakes": [m.to_dict() for m in all_mistakes],
        "landing_metrics": landing_metrics,
        "phase_events": recorder.phase_events,
    }
