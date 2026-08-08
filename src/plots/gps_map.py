"""Registry and figure builder for the GPS track map."""

from enum import StrEnum
from typing import Final, NamedTuple

import deal
import plotly.graph_objects as go
import polars as pl

from errors import AnalysisError


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


_MAP_STYLE: Final = "open-street-map"
"""Basemap style; free and token-free with go.Scattermap."""

_TRACK_COLOR: Final = "#37474f"
"""Neutral slate grey for the connecting line — stays legible against the
OSM basemap and, drawn thin beneath the coloured markers, doesn't compete
with any metric's colourscale."""

_MARKER_SIZE: Final = 6

_COLOR_RANGE_LOW_QUANTILE: Final = 0.02
_COLOR_RANGE_HIGH_QUANTILE: Final = 0.98
"""2nd/98th percentile as the colour range, so a single outlier reading
(sensor spike, brief sprint) doesn't wash out the colour scale for the rest
of the ride."""


@deal.pre(lambda values: values.drop_nulls().len() > 0)
def _percentile_color_range(values: pl.Series) -> tuple[float, float]:
    """Compute a percentile-clipped colour-scale range for a metric.

    Args:
        values: The metric's recorded (non-interpolated) values for the
            ride; must contain at least one non-null value.

    Returns:
        The ``(low, high)`` bounds, at the 2nd and 98th percentile.

    >>> import polars as pl
    >>> _percentile_color_range(pl.Series(range(1, 101)).cast(pl.Float64))
    (3.0, 98.0)
    """
    low = values.quantile(_COLOR_RANGE_LOW_QUANTILE)
    high = values.quantile(_COLOR_RANGE_HIGH_QUANTILE)
    return (low if low is not None else 0.0), (high if high is not None else 0.0)


def build_gps_map_figure(series: pl.DataFrame, metric: MetricKey) -> go.Figure:
    """Build a map of a workout's GPS track, coloured by the chosen metric.

    A GPS gap (e.g. a tunnel) is left as a break in the connecting line
    rather than bridged with a straight line to the next fix —
    ``latitude``/``longitude`` are passed through with their nulls intact,
    and ``connectgaps=False`` keeps plotly from drawing across them.

    A ride that revisits the same stretch of road (an out-and-back, or
    repeated loops for interval reps) draws several markers on top of each
    other at that spot. Markers are drawn in ascending order of their
    colour value, so whichever pass had the higher reading ends up on top —
    more useful for training analysis than an arbitrary draw order, since
    it surfaces the hardest effort at a spot rather than hiding it under an
    earlier, easier pass.

    A metric value missing at one GPS fix but present on both sides of it
    (e.g. a brief heart-rate dropout) is linearly interpolated for colour
    purposes only, so the coloured line doesn't visibly break for a single
    missing sample; a fix with no metric value on either side (the very
    start or end of a recording) is left out of the coloured markers
    entirely.

    Args:
        series: A time series built by :func:`plots.series.build_time_series`.
        metric: Which metric to colour the track by.

    Returns:
        A plotly figure with the track drawn on an OpenStreetMap basemap,
        zoomed and centred to the track's bounding box, with a colorbar
        labelled with the metric's name and unit.

    Raises:
        AnalysisError: If fewer than two records carry both a latitude and
            a longitude, or if ``metric`` has no data for this ride.

    >>> from datetime import UTC, datetime, timedelta
    >>> from models import RecordPoint
    >>> from plots.series import build_time_series
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [
    ...     RecordPoint(
    ...         timestamp=start, latitude=51.05, longitude=6.85, heart_rate=140
    ...     ),
    ...     RecordPoint(
    ...         timestamp=start + timedelta(seconds=1),
    ...         latitude=51.06,
    ...         longitude=6.86,
    ...         heart_rate=150,
    ...     ),
    ... ]
    >>> fig = build_gps_map_figure(build_time_series(records), MetricKey.HEART_RATE)
    >>> fig.data[1].marker.color.tolist()
    [140.0, 150.0]
    """
    fixes = series.filter(
        pl.col("latitude").is_not_null() & pl.col("longitude").is_not_null()
    )
    if len(fixes) < 2:
        raise AnalysisError("not enough GPS fixes to draw a track")

    spec = METRICS[metric]
    recorded_values = (
        fixes[spec.column].cast(pl.Float64).drop_nulls() * spec.conversion_factor
    )
    if recorded_values.len() == 0:
        raise AnalysisError(f"no data recorded for metric {metric.value!r}")
    low, high = _percentile_color_range(recorded_values)

    colorable = (
        series.with_columns(
            (pl.col(spec.column).cast(pl.Float64) * spec.conversion_factor)
            .interpolate()
            .alias("_color_value")
        )
        .filter(
            pl.col("latitude").is_not_null()
            & pl.col("longitude").is_not_null()
            & pl.col("_color_value").is_not_null()
        )
        .sort("_color_value")
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scattermap(
            lat=series["latitude"],
            lon=series["longitude"],
            mode="lines",
            line={"color": _TRACK_COLOR, "width": 2},
            connectgaps=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scattermap(
            lat=colorable["latitude"],
            lon=colorable["longitude"],
            mode="markers",
            marker={
                "color": colorable["_color_value"],
                "colorscale": spec.colorscale,
                "cmin": low,
                "cmax": high,
                "cmid": 0.0 if spec.scale is MetricScale.DIVERGING else None,
                "size": _MARKER_SIZE,
                "colorbar": {"title": {"text": f"{spec.label} ({spec.unit})"}},
            },
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        map={
            "style": _MAP_STYLE,
            "bounds": {
                "west": fixes["longitude"].min(),
                "east": fixes["longitude"].max(),
                "south": fixes["latitude"].min(),
                "north": fixes["latitude"].max(),
            },
        },
        showlegend=False,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        height=600,
    )
    return fig
