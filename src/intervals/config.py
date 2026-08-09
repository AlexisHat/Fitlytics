"""Tunable thresholds and window sizes for interval-block detection.

Centralised here, mirroring ``analysis.constants.PAUSE_GAP_THRESHOLD``, so a
tuning pass (see ``docs/entscheidungen.md``) touches one place instead of
chasing scattered magic numbers. Values are starting points for the first
implementation, not yet validated against real rides.
"""

from datetime import timedelta
from typing import Final

STANDSTILL_MIN_DURATION: Final = timedelta(seconds=20)
"""How long power (and speed, if recorded) must stay near zero before a
stretch counts as the rider stopped (e.g. a red light), not just coasting or
freewheeling."""

STANDSTILL_POWER_THRESHOLD_W: Final = 10
"""Power at or below this is "near zero" for standstill detection — a small
allowance for power-meter zero-offset drift, not literal 0 W."""

STANDSTILL_SPEED_THRESHOLD_MS: Final = 0.5
"""Speed at or below this (1.8 km/h) is "near zero" for standstill
detection — a small allowance for GPS jitter while stationary."""

BASELINE_WINDOW_S: Final = 600
"""Width, in seconds, of the centred rolling-median window used to estimate
a ride's local baseline power. Long enough to smooth over an interval
repetition without being so long it stops tracking a ride whose base
intensity drifts over its duration (e.g. warm-up vs. a climb)."""
