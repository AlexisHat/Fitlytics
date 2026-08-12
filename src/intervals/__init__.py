"""Automatic detection of interval blocks within a single workout."""

from intervals.blocks import (
    IntervalBlock,
    IntervalSummary,
    build_interval_block,
    build_interval_blocks,
    summarize_interval_blocks,
)
from intervals.config import DEFAULT_SCALE, Scale
from intervals.evaluation import Interval, IntervalEvaluation, evaluate, iou
from intervals.filtering import find_candidates
from intervals.preprocessing import compute_baseline, mark_standstill, resample_to_1hz
from intervals.synthetic import RideSegment, build_ride

__all__ = [
    "DEFAULT_SCALE",
    "Interval",
    "IntervalBlock",
    "IntervalEvaluation",
    "IntervalSummary",
    "RideSegment",
    "Scale",
    "build_interval_block",
    "build_interval_blocks",
    "build_ride",
    "compute_baseline",
    "evaluate",
    "find_candidates",
    "iou",
    "mark_standstill",
    "resample_to_1hz",
    "summarize_interval_blocks",
]
