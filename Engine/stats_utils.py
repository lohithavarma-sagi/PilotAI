"""
stats_utils.py

Small statistics helpers shared by mistake_detector.py and scoring_engine.py.
Pulled out to its own module so both can use the exact same math instead of
two copies quietly drifting apart.
"""

import math
from typing import List


def stdev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def circular_heading_stdev(headings_deg: List[float]) -> float:
    """Standard deviation of compass headings across the 0/360 wrap -- a
    heading wobbling between 359 and 1 is rock steady, not high-variance, so
    a plain stdev() on raw degrees would be wrong here.
    """
    if not headings_deg:
        return 0.0
    sin_sum = sum(math.sin(math.radians(h)) for h in headings_deg)
    cos_sum = sum(math.cos(math.radians(h)) for h in headings_deg)
    mean_angle = math.degrees(math.atan2(sin_sum, cos_sum))
    diffs = [((h - mean_angle + 180) % 360) - 180 for h in headings_deg]
    mean_diff = sum(diffs) / len(diffs)
    variance = sum((d - mean_diff) ** 2 for d in diffs) / len(diffs)
    return math.sqrt(variance)
