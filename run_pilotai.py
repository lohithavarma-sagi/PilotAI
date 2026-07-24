"""
run_pilotai.py

PilotAI's single Python entry point: analyze a completed flight and
generate the instructor report. No server, no dashboard, no networking --
see docs/ARCHITECTURE.md for why PilotAI moved to a fully local,
record-then-analyze workflow.

    python3 run_pilotai.py --test                 generate + analyze a synthetic flight (no simulator needed)
    python3 run_pilotai.py --analyze FLIGHT.json  analyze an already-recorded flight

The second form is what the C# Connector calls automatically the moment it
detects the engine has been shut down (see Connector/Program.cs) -- from a
student's point of view, they fly, shut the engine down, and the PDF is
just there. No manual step in between.
"""

import argparse
import datetime as dt
import json
import logging
import os
import platform
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
for sub in ("Engine", "Reports"):
    sys.path.insert(0, os.path.join(REPO_ROOT, sub))

from logging_setup import setup_logging  # noqa: E402
from synthetic_flight import generate_flight  # noqa: E402
from analyze import analyze_flight_file  # noqa: E402
from instructor_report import generate_full_report  # noqa: E402

logger = logging.getLogger("pilotai.launcher")


def _prompt_for_names(student_name, instructor_name):
    """Prompt for the two names on the title page, if not already given via
    CLI flags and stdin is an actual console (not a pipe/CI run). This is
    also what the C# Connector's console fills in interactively, since it
    launches this script with stdio inherited rather than redirected.
    """
    if student_name is None:
        if sys.stdin.isatty():
            typed = input("Student Pilot Name: ").strip()
            student_name = typed or None
    if instructor_name is None:
        if sys.stdin.isatty():
            typed = input("Instructor/Supervisor Name: ").strip()
            instructor_name = typed or None
    return student_name, instructor_name


def _open_file(path):
    """Best-effort auto-open of the generated PDF in the OS's default
    viewer. Never raises -- if this fails, the report still exists and its
    path was already printed.
    """
    try:
        system = platform.system()
        if system == "Darwin":
            subprocess.run(["open", path], check=False)
        elif system == "Windows":
            os.startfile(path)  # noqa: E1101 -- only exists on Windows
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception as exc:
        logger.info(f"Could not auto-open the PDF ({exc}) -- open it manually.")


def _print_completion_banner(paths):
    pdf_path = paths.get("pdf")
    print()
    print("=" * 60)
    if pdf_path:
        print("Flight analysis complete.")
        print()
        print("Report generated successfully.")
        print()
        print("PDF:")
        print(f"  {pdf_path}")
        print()
        print('Open on macOS:')
        print(f'  open "{pdf_path}"')
        print('Open on Windows:')
        print(f'  start "" "{pdf_path}"')
    else:
        print("Flight analysis complete (PDF generation failed -- see log).")
    print()
    print("All generated files:")
    for kind in ("pdf", "json", "text"):
        if kind in paths:
            print(f"  {kind.upper():5s} {paths[kind]}")
    print("=" * 60)


def _write_synthetic_recording(flights_dir: str, seed: int, sample_interval: float) -> str:
    os.makedirs(flights_dir, exist_ok=True)
    records = list(generate_flight(sample_interval=sample_interval, seed=seed))
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(flights_dir, f"test_flight_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    logger.info(f"Generated synthetic flight recording: {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description="Analyze a PilotAI flight recording and generate the instructor report.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--test", action="store_true", help="Generate and analyze a synthetic flight (no simulator needed).")
    mode.add_argument("--analyze", metavar="FLIGHT_FILE", help="Analyze an already-recorded flight file (.json or .csv).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for --test mode.")
    parser.add_argument("--sample-interval", type=float, default=0.5, help="Sample interval in seconds for --test mode.")
    parser.add_argument("--data-dir", default=os.path.join(REPO_ROOT, "Data"), help="Where flights/logs are stored.")
    parser.add_argument("--use-llm-summary", action="store_true",
                         help="Prefer a local LLM (see Reports/instructor_summary.py) for the Instructor Summary, "
                              "falling back to the offline template if it's not configured/reachable.")
    parser.add_argument("--student-name", default=None, help="Student pilot name for the report title page.")
    parser.add_argument("--instructor-name", default=None, help="Instructor/supervisor name for the report title page.")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open the generated PDF.")
    args = parser.parse_args()

    setup_logging(os.path.join(args.data_dir, "logs"))
    flights_dir = os.path.join(args.data_dir, "flights")

    if args.test:
        flight_path = _write_synthetic_recording(flights_dir, args.seed, args.sample_interval)
    else:
        flight_path = args.analyze

    student_name, instructor_name = _prompt_for_names(args.student_name, args.instructor_name)

    logger.info(f"Analyzing flight: {flight_path}")
    recorder, score_report, checklist_summary = analyze_flight_file(flight_path)
    logger.info(f"Overall score: {score_report['overall_score']}/100")

    paths = generate_full_report(recorder, score_report, checklist_summary, flight_path,
                                  use_llm_summary=args.use_llm_summary,
                                  student_name=student_name, instructor_name=instructor_name)
    logger.info(f"Report saved: {paths}")

    _print_completion_banner(paths)
    if not args.no_open and paths.get("pdf"):
        _open_file(paths["pdf"])

    return paths


if __name__ == "__main__":
    main()
