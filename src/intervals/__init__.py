"""Automatic detection of interval blocks within a single workout."""

from intervals.evaluation import Interval, IntervalEvaluation, evaluate, iou
from intervals.preprocessing import compute_baseline, mark_standstill, resample_to_1hz
from intervals.synthetic import RideSegment, build_ride

__all__ = [
    "Interval",
    "IntervalEvaluation",
    "RideSegment",
    "build_ride",
    "compute_baseline",
    "evaluate",
    "iou",
    "mark_standstill",
    "resample_to_1hz",
]
