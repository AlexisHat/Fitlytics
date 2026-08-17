"""Automatic detection of interval blocks within a single workout."""

from intervals.blocks import (
    IntervalBlock,
    IntervalSummary,
    build_interval_block,
    build_interval_blocks,
    summarize_interval_blocks,
)
from intervals.classification import (
    IntervalType,
    classify_block,
    classify_relative_power,
    classify_session,
)
from intervals.comparison import (
    PlanComparison,
    RepetitionComparison,
    compare_to_plan,
)
from intervals.detail import BlockDetail, block_detail, slice_block
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
    "BlockDetail",
    "Interval",
    "IntervalBlock",
    "IntervalEvaluation",
    "IntervalSummary",
    "IntervalType",
    "PlanComparison",
    "RepetitionComparison",
    "RideSegment",
    "block_detail",
    "build_interval_block",
    "build_interval_blocks",
    "build_ride",
    "classify_block",
    "classify_relative_power",
    "classify_session",
    "compare_to_plan",
    "effort_threshold",
    "evaluate",
    "find_candidates",
    "iou",
    "mark_standstill",
    "resample_to_1hz",
    "slice_block",
    "smooth_power",
    "summarize_interval_blocks",
]
