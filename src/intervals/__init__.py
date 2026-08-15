"""Automatic detection of interval blocks within a single workout."""

from intervals.blocks import (
    IntervalBlock,
    IntervalSummary,
    build_interval_block,
    build_interval_blocks,
    summarize_interval_blocks,
)
from intervals.evaluation import Interval, IntervalEvaluation, evaluate, iou
from intervals.preprocessing import (
    effort_threshold,
    mark_standstill,
    resample_to_1hz,
    smooth_power,
)
from intervals.selection import find_candidates
from intervals.synthetic import RideSegment, build_ride

__all__ = [
    "Interval",
    "IntervalBlock",
    "IntervalEvaluation",
    "IntervalSummary",
    "RideSegment",
    "build_interval_block",
    "build_interval_blocks",
    "build_ride",
    "effort_threshold",
    "evaluate",
    "find_candidates",
    "iou",
    "mark_standstill",
    "resample_to_1hz",
    "smooth_power",
    "summarize_interval_blocks",
]
