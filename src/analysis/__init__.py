"""Computation of training metrics from imported data."""

from analysis.metrics import average
from analysis.workout import WorkoutMetrics, compute_workout_metrics

__all__ = ["WorkoutMetrics", "average", "compute_workout_metrics"]
