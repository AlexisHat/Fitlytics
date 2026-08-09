"""The eight mandatory synthetic-ride scenarios for tuning interval detection.

Each function builds one of the required test cases from the segmentation
design (5x4min, noisy fatigue, sprints with pauses, ...), so later
milestones (candidate search, consolidation, tuning) validate against the
same fixed set of rides instead of everyone inventing their own variant.
"""

from intervals.evaluation import Interval
from intervals.synthetic import RideSegment, build_ride
from models import RecordPoint

_WARMUP_POWER_W = 100.0
_INTERVAL_POWER_W = 250.0
_RECOVERY_POWER_W = 100.0


def clean_5x4min(seed: int = 0) -> tuple[list[RecordPoint], list[Interval]]:
    """5x4min intervals at a steady power, with little noise.

    Args:
        seed: Seed for the ride's noise, for reproducibility.

    Returns:
        The ride's records and its 5 reference interval blocks.

    >>> records, reference = clean_5x4min()
    >>> len(reference)
    5
    """
    segments = [RideSegment(120, _WARMUP_POWER_W, noise_std_w=3.0)]
    for rep in range(5):
        segments.append(
            RideSegment(240, _INTERVAL_POWER_W, is_interval=True, noise_std_w=3.0)
        )
        if rep < 4:
            segments.append(RideSegment(180, _RECOVERY_POWER_W, noise_std_w=3.0))
    return build_ride(segments, seed=seed)


def noisy_5x4min_with_fatigue(
    seed: int = 0,
) -> tuple[list[RecordPoint], list[Interval]]:
    """5x4min intervals with heavy noise and a fading target power per rep.

    Args:
        seed: Seed for the ride's noise, for reproducibility.

    Returns:
        The ride's records and its 5 reference interval blocks.

    >>> records, reference = noisy_5x4min_with_fatigue()
    >>> len(reference)
    5
    """
    rep_powers = [260.0, 250.0, 240.0, 230.0, 220.0]
    segments = [RideSegment(120, _WARMUP_POWER_W, noise_std_w=10.0)]
    for rep, power in enumerate(rep_powers):
        segments.append(RideSegment(240, power, is_interval=True, noise_std_w=25.0))
        if rep < len(rep_powers) - 1:
            segments.append(RideSegment(180, _RECOVERY_POWER_W, noise_std_w=10.0))
    return build_ride(segments, seed=seed)


def ten_by_30s_with_pauses(seed: int = 0) -> tuple[list[RecordPoint], list[Interval]]:
    """10x30s sprints, each followed by a full 30s stop.

    Args:
        seed: Seed for the ride's noise, for reproducibility.

    Returns:
        The ride's records and its 10 reference interval blocks.

    >>> records, reference = ten_by_30s_with_pauses()
    >>> len(reference)
    10
    """
    segments: list[RideSegment] = []
    for _ in range(10):
        segments.append(RideSegment(30, 400.0, is_interval=True, noise_std_w=15.0))
        segments.append(RideSegment(30, 0.0, noise_std_w=1.0))
    return build_ride(segments, seed=seed)


def two_by_20min(seed: int = 0) -> tuple[list[RecordPoint], list[Interval]]:
    """2x20min steady intervals with a long recovery between them.

    Args:
        seed: Seed for the ride's noise, for reproducibility.

    Returns:
        The ride's records and its 2 reference interval blocks.

    >>> records, reference = two_by_20min()
    >>> len(reference)
    2
    """
    segments = [
        RideSegment(1200, 220.0, is_interval=True, noise_std_w=8.0),
        RideSegment(300, _RECOVERY_POWER_W, noise_std_w=8.0),
        RideSegment(1200, 220.0, is_interval=True, noise_std_w=8.0),
    ]
    return build_ride(segments, seed=seed)


def single_1min_block_in_warmup(
    seed: int = 0,
) -> tuple[list[RecordPoint], list[Interval]]:
    """One 1-minute block early in a long warm-up, nothing after it.

    Args:
        seed: Seed for the ride's noise, for reproducibility.

    Returns:
        The ride's records and its single reference interval block.

    >>> records, reference = single_1min_block_in_warmup()
    >>> len(reference)
    1
    """
    segments = [
        RideSegment(180, _WARMUP_POWER_W, noise_std_w=5.0),
        RideSegment(60, 300.0, is_interval=True, noise_std_w=5.0),
        RideSegment(1200, _WARMUP_POWER_W, noise_std_w=5.0),
    ]
    return build_ride(segments, seed=seed)


def rolling_terrain_no_intervals(
    seed: int = 0,
) -> tuple[list[RecordPoint], list[Interval]]:
    """Undulating power from terrain alone — no real interval anywhere.

    Args:
        seed: Seed for the ride's noise, for reproducibility.

    Returns:
        The ride's records and an empty reference list.

    >>> records, reference = rolling_terrain_no_intervals()
    >>> reference
    []
    """
    segments = [
        RideSegment(90, 150.0, noise_std_w=10.0),
        RideSegment(60, 190.0, noise_std_w=10.0),
        RideSegment(120, 140.0, noise_std_w=10.0),
        RideSegment(90, 180.0, noise_std_w=10.0),
        RideSegment(150, 160.0, noise_std_w=10.0),
    ]
    return build_ride(segments, seed=seed)


def traffic_light_stop_mid_block(
    seed: int = 0,
) -> tuple[list[RecordPoint], list[Interval]]:
    """A single interval interrupted by a stop too brief to split it.

    Args:
        seed: Seed for the ride's noise, for reproducibility.

    Returns:
        The ride's records and its single, continuous reference interval
        block spanning both power segments and the brief stop between them.

    >>> records, reference = traffic_light_stop_mid_block()
    >>> len(reference)
    1
    """
    segments = [
        RideSegment(240, _INTERVAL_POWER_W, is_interval=True, noise_std_w=5.0),
        RideSegment(12, 0.0, is_interval=True, noise_std_w=1.0),
        RideSegment(240, _INTERVAL_POWER_W, is_interval=True, noise_std_w=5.0),
    ]
    return build_ride(segments, seed=seed)


def recording_gap_mid_block(seed: int = 0) -> tuple[list[RecordPoint], list[Interval]]:
    """An interval-shaped ride with a genuine recording gap through the middle.

    Args:
        seed: Seed for the ride's noise, for reproducibility.

    Returns:
        The ride's records (with a real timestamp gap in the middle) and
        its two reference interval blocks — a gap always splits a block.

    >>> records, reference = recording_gap_mid_block()
    >>> len(reference)
    2
    """
    segments = [
        RideSegment(240, _INTERVAL_POWER_W, is_interval=True, noise_std_w=5.0),
        RideSegment(60, None),
        RideSegment(240, _INTERVAL_POWER_W, is_interval=True, noise_std_w=5.0),
    ]
    return build_ride(segments, seed=seed)
