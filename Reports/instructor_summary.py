"""
instructor_summary.py

Generates the "Instructor Summary" section of the report: a short,
narrative evaluation covering overall performance, strengths, weaknesses,
recommended practice areas, and an encouraging closing remark -- written to
read like something a real CFI would hand a student, not a dump of
numbers.

This is NOT a trained model (see Engine/scoring_engine.py's docstring for
the reasoning that applies here too). By default it's a template-based
generator: deterministic, offline, and free, built entirely from the
already-computed scores/mistakes/strengths -- the whole point is that
PilotAI works with zero setup and zero ongoing cost.

The generator is modular specifically so a local LLM can optionally take
over prose generation without changing anything else in the report
pipeline. "Local" is the operative word: SummaryBackend implementations
here only ever talk to a backend on localhost (e.g. Ollama), never a cloud
API, so turning this on never adds a paid service or a network dependency
PilotAI doesn't already have. It's opt-in and off by default; if the local
endpoint is unreachable for any reason, generation silently falls back to
the template backend rather than failing the whole report.
"""

import json
import logging
import os
import urllib.request
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger("pilotai.instructor_summary")

GRADE_BANDS = [
    (90, "Excellent"),
    (80, "Good"),
    (70, "Satisfactory"),
    (60, "Developing"),
    (0, "Needs Improvement"),
]


def grade_label(score: int) -> str:
    for threshold, label in GRADE_BANDS:
        if score >= threshold:
            return label
    return "Needs Improvement"


def letter_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


class SummaryBackend(Protocol):
    def generate(self, report: Dict[str, Any]) -> Optional[str]:
        """Return summary text, or None to fall back to the next backend."""
        ...


class TemplateSummaryBackend:
    """The default, always-available, fully offline summary generator."""

    def generate(self, report: Dict[str, Any]) -> Optional[str]:
        overall = report["scores"]["overall_score"]
        categories = report["scores"]["categories"]
        mistakes = report.get("mistakes", [])
        aircraft = report.get("aircraft", "the aircraft")

        strengths = self._top_strengths(categories)
        weaknesses = self._top_weaknesses(mistakes)
        practice_areas = self._practice_areas(mistakes)

        paragraphs = [
            self._overall_paragraph(overall, aircraft, report),
            self._strengths_paragraph(strengths),
            self._weaknesses_paragraph(weaknesses),
            self._practice_paragraph(practice_areas),
            self._closing_paragraph(overall),
        ]
        return "\n\n".join(p for p in paragraphs if p)

    def _top_strengths(self, categories: Dict[str, Any], limit: int = 4) -> List[str]:
        strengths = []
        for cat in categories.values():
            strengths.extend(cat.get("strengths", []))
        return strengths[:limit]

    def _top_weaknesses(self, mistakes: List[Dict[str, Any]], limit: int = 4) -> List[Dict[str, Any]]:
        severity_rank = {"major": 0, "moderate": 1, "minor": 2}
        ranked = sorted(mistakes, key=lambda m: severity_rank.get(m["severity"], 3))
        return ranked[:limit]

    def _practice_areas(self, mistakes: List[Dict[str, Any]], limit: int = 3) -> List[str]:
        severity_rank = {"major": 0, "moderate": 1, "minor": 2}
        ranked = sorted(mistakes, key=lambda m: severity_rank.get(m["severity"], 3))
        seen = []
        for m in ranked:
            rec = m.get("recommendation")
            if rec and rec not in seen:
                seen.append(rec)
            if len(seen) >= limit:
                break
        return seen

    def _overall_paragraph(self, overall: int, aircraft: str, report: Dict[str, Any]) -> str:
        label = grade_label(overall).lower()
        duration = report.get("flight_summary", {}).get("duration_str", "this flight")
        if overall >= 90:
            opener = f"This was an excellent flight in the {aircraft}."
        elif overall >= 80:
            opener = f"This was a good, solid flight in the {aircraft}."
        elif overall >= 70:
            opener = f"This was a satisfactory flight in the {aircraft}, with room to grow."
        elif overall >= 60:
            opener = f"This flight in the {aircraft} showed a developing skill set, with several areas needing attention."
        else:
            opener = f"This flight in the {aircraft} highlighted several fundamentals that need focused work."
        return f"{opener} Overall performance over {duration} scored {overall}/100 ({label})."

    def _strengths_paragraph(self, strengths: List[str]) -> str:
        if not strengths:
            return "No specific strengths stood out as exceptional this flight -- focus on the fundamentals below."
        if len(strengths) == 1:
            body = strengths[0].rstrip(".")
            return f"Strengths: {body}."
        listed = "; ".join(s.rstrip(".").lower() if i > 0 else s.rstrip(".") for i, s in enumerate(strengths))
        return f"Strengths: {listed}."

    def _weaknesses_paragraph(self, weaknesses: List[Dict[str, Any]]) -> str:
        if not weaknesses:
            return "No significant weaknesses were identified this flight."
        parts = [f"{w['phase'].lower()} -- {w['explanation'].rstrip('.').lower()}" for w in weaknesses]
        return "Weaknesses: " + "; ".join(parts) + "."

    def _practice_paragraph(self, practice_areas: List[str]) -> str:
        if not practice_areas:
            return "Recommended practice: continue flying similar profiles to build consistency."
        listed = " ".join(practice_areas)
        return f"Recommended practice areas: {listed}"

    def _closing_paragraph(self, overall: int) -> str:
        if overall >= 90:
            return "Excellent work -- keep flying to this standard and start looking ahead to more advanced maneuvers."
        if overall >= 80:
            return "Solid flight overall. A little more focus on the points above and this will be an excellent flight next time."
        if overall >= 70:
            return "A reasonable flight with clear, specific things to work on. Keep at it -- progress is steady."
        if overall >= 60:
            return "There's a solid foundation here. Focus on the recommended practice areas and the next flight will show real improvement."
        return "Every pilot has flights like this on the way up. Focus on one or two of the items above at a time, and revisit this report before the next lesson."


class LocalLLMSummaryBackend:
    """Optional: if a local LLM server (e.g. Ollama on localhost) is
    configured, use it to generate more natural prose from the same report
    data. Never contacts anything other than the configured local endpoint,
    and any failure (not configured, not running, timeout, bad response)
    falls back silently -- this must never be the reason a report fails to
    generate.
    """

    def __init__(self, endpoint: Optional[str] = None, model: Optional[str] = None, timeout_sec: float = 8.0):
        self.endpoint = endpoint or os.environ.get("PILOTAI_LLM_ENDPOINT")
        self.model = model or os.environ.get("PILOTAI_LLM_MODEL", "llama3")
        self.timeout_sec = timeout_sec

    def generate(self, report: Dict[str, Any]) -> Optional[str]:
        if not self.endpoint:
            return None
        try:
            prompt = self._build_prompt(report)
            payload = json.dumps({"model": self.model, "prompt": prompt, "stream": False}).encode("utf-8")
            req = urllib.request.Request(
                self.endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data.get("response", "").strip()
            return text or None
        except Exception as exc:
            logger.info(f"Local LLM summary backend unavailable ({exc}) -- falling back to template summary.")
            return None

    def _build_prompt(self, report: Dict[str, Any]) -> str:
        overall = report["scores"]["overall_score"]
        categories = {name: c["score"] for name, c in report["scores"]["categories"].items()}
        mistakes = [m["explanation"] for m in report.get("mistakes", [])]
        return (
            "You are an experienced flight instructor writing a short evaluation for a student "
            "after a Cessna 172 training flight. Be specific, encouraging, and professional. "
            "Cover: overall performance, strengths, weaknesses, recommended practice areas, and "
            "an encouraging closing remark.\n\n"
            f"Overall score: {overall}/100\n"
            f"Category scores: {categories}\n"
            f"Detected issues: {mistakes}\n"
        )


def generate_instructor_summary(report: Dict[str, Any], use_llm: bool = False) -> str:
    """Build the Instructor Summary text. Template-based by default (fully
    offline); pass use_llm=True to prefer a configured local LLM, falling
    back to the template automatically if it's unavailable.
    """
    if use_llm:
        llm_text = LocalLLMSummaryBackend().generate(report)
        if llm_text:
            return llm_text
    return TemplateSummaryBackend().generate(report)
