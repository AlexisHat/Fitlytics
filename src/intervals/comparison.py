"""Measuring a session's detected blocks against the athlete's own plan.

Strictly a reporting layer: the plan is a statement of intent entered at
upload time and never feeds back into detection. Keeping the two apart
matters because plans are routinely wrong — a session labelled 2x9min can
turn out to be three efforts of eight — and a detector told what to look
for would simply confirm the label instead of measuring the ride.
"""

from datetime import timedelta

import deal
from pydantic import BaseModel, NonNegativeFloat, NonNegativeInt, PositiveInt

from analysis import average
from intervals.blocks import IntervalBlock
from models import PlannedIntervalSpec


class RepetitionComparison(BaseModel):
    """One ridden repetition measured against what the plan called for.

    Attributes:
        duration: How long the repetition actually lasted.
        duration_deviation: ``duration`` minus the planned duration.
            Negative means the repetition was cut short.
        avg_power_w: Mean power actually held during the repetition.
        power_deviation_w: ``avg_power_w`` minus the planned target.
            Negative means the target was missed.
    """

    duration: timedelta
    duration_deviation: timedelta
    avg_power_w: NonNegativeFloat
    power_deviation_w: float


class PlanComparison(BaseModel):
    """A session's detected blocks measured against the athlete's plan.

    Attributes:
        planned_repetitions: How many repeats the plan called for.
        detected_repetitions: How many blocks detection actually found.
            May differ from ``planned_repetitions`` in either direction.
        repetitions: One entry per detected block, chronologically.
        mean_power_deviation_w: Mean of the per-repetition power
            deviations. Positive means the session was ridden harder than
            planned.
    """

    planned_repetitions: PositiveInt
    detected_repetitions: NonNegativeInt
    repetitions: list[RepetitionComparison]
    mean_power_deviation_w: float


@deal.pre(lambda blocks, plan: len(blocks) > 0)
@deal.ensure(lambda _: len(_.result.repetitions) == len(_.blocks))
@deal.ensure(lambda _: _.result.detected_repetitions == len(_.blocks))
def compare_to_plan(
    blocks: list[IntervalBlock], plan: PlannedIntervalSpec
) -> PlanComparison:
    """Compare a session's detected interval blocks against its plan.

    Every detected block is reported, including any beyond the number the
    plan called for — an extra effort is information about the ride, not
    an error to be trimmed away to make the counts match.

    Args:
        blocks: The session's detected interval blocks, in chronological
            order; must not be empty.
        plan: The interval structure the athlete entered at upload time.

    Returns:
        The comparison, with one entry per detected block.

    Raises:
        deal.PreContractError: If ``blocks`` is empty.

    >>> from datetime import UTC, datetime, timedelta
    >>> start = datetime(2026, 1, 1, tzinfo=UTC)
    >>> block = IntervalBlock(
    ...     start=start,
    ...     end=start + timedelta(minutes=4),
    ...     duration=timedelta(minutes=4),
    ...     avg_power_w=260.0,
    ...     avg_power_relative_to_ftp=None,
    ...     avg_heart_rate=None,
    ...     heart_rate_drift_bpm=None,
    ...     evenness=1.0,
    ... )
    >>> plan = PlannedIntervalSpec(
    ...     repetitions=2, duration=timedelta(minutes=5), target_power_w=250
    ... )
    >>> comparison = compare_to_plan([block], plan)
    >>> comparison.planned_repetitions, comparison.detected_repetitions
    (2, 1)
    >>> comparison.repetitions[0].duration_deviation.total_seconds()
    -60.0
    >>> comparison.repetitions[0].power_deviation_w
    10.0
    """
    repetitions = [
        RepetitionComparison(
            duration=block.duration,
            duration_deviation=block.duration - plan.duration,
            avg_power_w=block.avg_power_w,
            power_deviation_w=block.avg_power_w - plan.target_power_w,
        )
        for block in blocks
    ]
    return PlanComparison(
        planned_repetitions=plan.repetitions,
        detected_repetitions=len(blocks),
        repetitions=repetitions,
        mean_power_deviation_w=average(
            [repetition.power_deviation_w for repetition in repetitions]
        ),
    )
