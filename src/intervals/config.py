"""Tunable thresholds and window sizes for interval-block detection.

Centralised here, mirroring ``analysis.constants.PAUSE_GAP_THRESHOLD``, so a
tuning pass (see ``docs/entscheidungen.md``) touches one place instead of
chasing scattered magic numbers. The values below are listed in the order
the pipeline applies them, and each was calibrated against real rides
rather than guessed.
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

SMOOTHING_WINDOW_S: Final = 30
"""Width, in seconds, of the centred rolling mean applied to power before
any block detection. Raw 1 Hz power swings by a median of ~12 W from one
second to the next even mid-effort, which makes any threshold on the raw
signal cross back and forth constantly and shatter one real effort into
dozens of fragments. Thirty seconds is long enough to remove that chatter
and short enough to keep the start and end of a real effort within a few
seconds of their true position."""

COASTING_POWER_W: Final = 20
"""Power at or below this counts as coasting rather than riding, and is
left out of the two-class split that derives the effort threshold (see
``preprocessing.effort_threshold``). A long descent is not a statement
about how hard a ride was, and leaving it in creates a spurious third
class of near-zero readings for the split to latch onto."""

OTSU_BINS: Final = 64
"""How finely the ride's power readings are histogrammed when splitting
them into an easy and a hard class (see ``preprocessing.effort_threshold``).
Sixty-four bins put the threshold within a few watts of the exact optimum
across the whole plausible power range, which is far below the precision
the smoothing step leaves intact anyway."""

MERGE_GAP_S: Final = 45
"""Longest dip below the threshold that still counts as "inside" one
effort rather than the boundary between two. Measured on real rides: a
single 8 s ease-off and a 26 s one split what were plainly two continuous
efforts, so anything shorter than roughly a minute has to bridge."""

MIN_BLOCK_DURATION_S: Final = 120
"""Shortest stretch reported as an interval block. Below this, ordinary
terrain — a short rise, a sprint out of a junction — is indistinguishable
from a deliberate effort on power alone."""

KEEP_FRACTION: Final = 0.80
"""How close to the session's strongest block a candidate must come to be
kept (see ``selection.select_consistent``). Interval repetitions within one
session are deliberately ridden at a similar power, so a candidate far
below the strongest is warm-up or terrain rather than one of the reps."""
