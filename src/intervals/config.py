"""Tunable thresholds and window sizes for interval-block detection.

Centralised here, mirroring ``analysis.constants.PAUSE_GAP_THRESHOLD``, so a
tuning pass (see ``docs/entscheidungen.md``) touches one place instead of
chasing scattered magic numbers. Values are starting points for the first
implementation, not yet validated against real rides.
"""

from datetime import timedelta
from typing import Final, NamedTuple

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


class Scale(NamedTuple):
    """Tuning parameters for one sliding-window time scale of candidate search.

    Attributes:
        name: Short identifier, e.g. ``"mittel"``, used only for
            diagnostics.
        smoothing_window_s: Width of the centred moving-average window
            applied to power before edge-finding; should be at most half
            this scale's target block duration, or a block gets smeared
            past recognition.
        min_duration_s: Shortest candidate this scale accepts.
        prominence_ws: Minimum CUSUM-peak prominence, in watt-seconds, for
            an edge to count as real rather than noise. Deliberately well
            below a genuine block's own prominence (a 4-minute block ~150 W
            above baseline integrates to tens of thousands of watt-seconds)
            — this only needs to filter out noise-level fluctuations, the
            elevation and duration filters do the real, baseline-relative
            filtering later.
        merge_gap_s: Longest gap between two candidates of this scale that
            still counts as "close enough" to merge into one.
    """

    name: str
    smoothing_window_s: int
    min_duration_s: int
    prominence_ws: float
    merge_gap_s: int


MEDIUM_SCALE: Final = Scale(
    name="mittel",
    smoothing_window_s=20,
    min_duration_s=60,
    prominence_ws=300.0,
    merge_gap_s=12,
)
"""Targets 1-8 minute blocks (threshold efforts, sweet spot, VO2max) — see
docs/entscheidungen.md for the scale table this is the first entry of."""

HYSTERESIS_ENTRY_FRACTION: Final = 0.9
"""Fraction of a candidate's estimated target power that the signal must
rise above for its start edge to count as "entered"."""

HYSTERESIS_EXIT_FRACTION: Final = 0.7
"""Fraction of a candidate's estimated target power that the signal must
fall below for its end edge to count as "exited". Lower than the entry
fraction on purpose: a single, higher threshold would end a block at every
minor dip, which is the most common failure mode on outdoor rides."""

MIN_ELEVATION_ABOVE_BASELINE_FRACTION: Final = 0.15
"""A candidate's power must exceed the local baseline by at least this
fraction to count as a real effort rather than a ripple in the base pace."""

MAX_HOMOGENEITY_CV: Final = 0.25
"""Maximum coefficient of variation (std / mean) of power within a
candidate. A block that swings this wildly internally is more likely
wavy terrain than a deliberate, steady effort."""
