"""Registry and figure builder for the GPS track map."""

from enum import StrEnum
from typing import Final, NamedTuple

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
"""Neutral slate grey — stays legible against the OSM basemap and, once a
metric colours the track (a later commit), still works as the thin
connecting line drawn underneath the coloured markers."""


def build_gps_map_figure(series: pl.DataFrame) -> go.Figure:
    """Build a single-colour map of a workout's GPS track.

    A GPS gap (e.g. a tunnel) is left as a break in the line rather than
    bridged with a straight line to the next fix — ``latitude``/``longitude``
    are passed through with their nulls intact, and ``connectgaps=False``
    keeps plotly from drawing across them.

    Args:
        series: A time series built by :func:`plots.series.build_time_series`.

    Returns:
        A plotly figure with the track drawn on an OpenStreetMap basemap,
        zoomed and centred to the track's bounding box.

    Raises:
        AnalysisError: If fewer than two records carry both a latitude and
            a longitude.

    >>> from datetime import UTC, datetime, timedelta
    >>> from models import RecordPoint
    >>> from plots.series import build_time_series
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [
    ...     RecordPoint(timestamp=start, latitude=51.05, longitude=6.85),
    ...     RecordPoint(
    ...         timestamp=start + timedelta(seconds=1), latitude=51.06, longitude=6.86
    ...     ),
    ... ]
    >>> fig = build_gps_map_figure(build_time_series(records))
    >>> bounds = fig.layout.map.bounds
    >>> (bounds.west, bounds.east, bounds.south, bounds.north)
    (6.85, 6.86, 51.05, 51.06)
    """
    fixes = series.filter(
        pl.col("latitude").is_not_null() & pl.col("longitude").is_not_null()
    )
    if len(fixes) < 2:
        raise AnalysisError("not enough GPS fixes to draw a track")

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
