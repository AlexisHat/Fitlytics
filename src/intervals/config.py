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
"""Width, in seconds, of the centred rolling window used to estimate a
ride's local baseline power. Long enough to smooth over an interval
repetition without being so long it stops tracking a ride whose base
intensity drifts over its duration (e.g. warm-up vs. a climb)."""

BASELINE_QUANTILE: Final = 0.25
"""Which rolling quantile of power counts as "baseline", not the median
(0.5). A block's own repetitions can occupy a large share of the window (a
5x4min session is more than half work), so the median often sits at or
near the block's own power instead of the recovery level it's meant to
represent. A low quantile stays anchored to the recovery/easy-riding level
as long as some meaningful share of the window is spent there."""


class Scale(NamedTuple):
    """Tuning parameters for one sliding-window time scale of candidate search.

    Attributes:
        name: Short identifier, e.g. ``"mittel"``, used only for
            diagnostics.
        min_duration_s: Shortest candidate this scale accepts.
        merge_gap_s: Longest gap between two candidates of this scale that
            still counts as "close enough" to merge into one.
    """

    name: str
    min_duration_s: int
    merge_gap_s: int


MEDIUM_SCALE: Final = Scale(name="mittel", min_duration_s=60, merge_gap_s=12)
"""Targets 1-8 minute blocks (threshold efforts, sweet spot, VO2max) — see
docs/entscheidungen.md for the scale table this is the first entry of."""

HYSTERESIS_ENTRY_FRACTION: Final = 0.20
"""How far above the local baseline power must rise, as a fraction of the
baseline itself, before a stretch counts as "entered" a block."""

HYSTERESIS_EXIT_FRACTION: Final = 0.08
"""How far above the local baseline power must stay to still count as
"inside" a block once entered. Lower than the entry fraction on purpose: a
single, shared threshold would end a block at every minor dip, which is the
most common failure mode on outdoor rides."""

MIN_ELEVATION_ABOVE_BASELINE_FRACTION: Final = 0.15
"""A candidate's power must exceed the local baseline by at least this
fraction to count as a real effort rather than a ripple in the base pace."""

MAX_HOMOGENEITY_CV: Final = 0.25
"""Maximum coefficient of variation (std / mean) of power within a
candidate. A block that swings this wildly internally is more likely
wavy terrain than a deliberate, steady effort."""
