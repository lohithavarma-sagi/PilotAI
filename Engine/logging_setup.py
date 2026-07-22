"""
logging_setup.py

Central logging configuration for all of PilotAI. Every module just does
`logging.getLogger("pilotai.<module>")` and writes normally -- this file is
the only place that decides where those messages actually go: a rotating
log file under Data/logs/, and the console.

Captures errors, warnings, connection issues, flight events, and SimConnect
reconnects (as logged by telemetry_source.py) -- the "Logging" requirement
in the spec is this file plus every logger.info/warning/error call
throughout Engine/.
"""

import logging
import logging.handlers
import os


def setup_logging(log_dir: str, level: int = logging.INFO) -> None:
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "pilotai.log")

    root = logging.getLogger("pilotai")
    root.setLevel(level)
    root.handlers.clear()

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))
    root.addHandler(console_handler)

    root.info(f"Logging initialized -> {log_path}")
