"""Automatic detection of interval blocks within a single workout."""

from intervals.config import MEDIUM_SCALE, Scale
from intervals.evaluation import Interval, IntervalEvaluation, evaluate, iou
from intervals.filtering import find_candidates
from intervals.preprocessing import compute_baseline, mark_standstill, resample_to_1hz
from intervals.synthetic import RideSegment, build_ride

__all__ = [
    "MEDIUM_SCALE",
    "Interval",
    "IntervalEvaluation",
    "RideSegment",
    "Scale",
    "build_ride",
    "compute_baseline",
    "evaluate",
    "find_candidates",
    "iou",
    "mark_standstill",
    "resample_to_1hz",
]
