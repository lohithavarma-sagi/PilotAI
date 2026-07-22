"""
run_all.py

Runs every test in Tests/ and prints a pass/fail summary. No pytest
dependency -- stdlib unittest discovery is enough for this project's size.

    python3 Tests/run_all.py
"""

import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=TESTS_DIR, pattern="test_*.py", top_level_dir=TESTS_DIR)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
