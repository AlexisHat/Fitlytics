"""Automatic detection of interval blocks within a single workout."""

from intervals.preprocessing import compute_baseline, mark_standstill, resample_to_1hz

__all__ = ["compute_baseline", "mark_standstill", "resample_to_1hz"]
