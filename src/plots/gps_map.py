"""Registry of colourable metrics for the GPS track map."""

from enum import StrEnum
from typing import Final, NamedTuple

import polars as pl


class MetricScale(StrEnum):
    """How a colourable metric's values map onto its colourscale.

    Attributes:
        SEQUENTIAL: Low to high, e.g. power or heart rate.
        DIVERGING: Centred on zero, e.g. gradient (climb vs. descent).
    """

    SEQUENTIAL = "sequential"
    DIVERGING = "diverging"


class MetricKey(StrEnum):
    """Stable identifier for a colourable metric, selectable by the UI.

    Attributes:
        POWER: Instantaneous power in watts.
        SPEED: Speed in km/h.
        HEART_RATE: Heart rate in bpm.
        GRADE: Instantaneous gradient in percent.
        CADENCE: Pedalling cadence in rpm.
    """

    POWER = "power"
    SPEED = "speed"
    HEART_RATE = "heart_rate"
    GRADE = "grade"
    CADENCE = "cadence"


class MetricSpec(NamedTuple):
    """Display and scaling configuration for one colourable metric.

    Attributes:
        column: Column of the time series (see
            :func:`plots.series.build_time_series`) this metric's colour
            comes from.
        label: German display name, e.g. for the colorbar title.
        unit: Unit shown alongside the value, e.g. ``"W"``.
        conversion_factor: Factor applied to the column's value before
            display; 1.0 unless a metric needs a unit conversion the time
            series does not already apply.
        colorscale: Plotly colorscale name.
        scale: Whether the colour range is sequential or diverging around
            zero.
    """

    column: str
    label: str
    unit: str
    conversion_factor: float
    colorscale: str
    scale: MetricScale = MetricScale.SEQUENTIAL


METRICS: Final[dict[MetricKey, MetricSpec]] = {
    MetricKey.POWER: MetricSpec("power", "Leistung", "W", 1.0, "Plasma"),
    MetricKey.SPEED: MetricSpec("speed_kmh", "Geschwindigkeit", "km/h", 1.0, "Viridis"),
    MetricKey.HEART_RATE: MetricSpec(
        "heart_rate", "Herzfrequenz", "bpm", 1.0, "YlOrRd"
    ),
    MetricKey.GRADE: MetricSpec(
        "grade_pct", "Steigung", "%", 1.0, "RdBu", MetricScale.DIVERGING
    ),
    MetricKey.CADENCE: MetricSpec("cadence", "Trittfrequenz", "rpm", 1.0, "Cividis"),
}
"""Every metric the map plot can colour a track by. Adding a new colourable
metric means adding an entry here — the plot builder (added in a later
commit) reads this table generically and needs no change of its own."""


def available_metrics(series: pl.DataFrame) -> tuple[MetricKey, ...]:
    """Report which colourable metrics actually carry data for a ride.

    Args:
        series: A time series built by :func:`plots.series.build_time_series`.

    Returns:
        The metric keys, in :data:`METRICS`' order, whose source column has
        at least one non-null value.

    >>> from datetime import UTC, datetime
    >>> from models import RecordPoint
    >>> from plots.series import build_time_series
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [RecordPoint(timestamp=start, heart_rate=140)]
    >>> [key.value for key in available_metrics(build_time_series(records))]
    ['heart_rate']
    """
    return tuple(
        key
        for key, spec in METRICS.items()
        if series[spec.column].drop_nulls().len() > 0
    )
