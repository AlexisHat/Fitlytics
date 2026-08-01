"""Panel-driven multi-panel figure for a single workout's time series."""

from typing import Final, NamedTuple

import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from errors import AnalysisError
from plots.series import available_channels


class _PanelSpec(NamedTuple):
    """One subplot's data column, label and line styling.

    Attributes:
        column: Column of the time series this panel plots.
        title: German panel title, used as both the subplot heading and
            the trace name.
        color: Line (and, if filled, fill) colour as a hex string.
        fill: Whether to fill the area under the line down to the axis
            baseline, e.g. for a terrain-profile look.
    """

    column: str
    title: str
    color: str
    fill: bool = False


_PANELS: Final[tuple[_PanelSpec, ...]] = (
    _PanelSpec("altitude_m", "Höhe (m)", "#a0785a", fill=True),
    _PanelSpec("power", "Leistung (W)", "#d62728"),
    _PanelSpec("heart_rate", "Herzfrequenz (bpm)", "#2ca02c"),
    _PanelSpec("speed_kmh", "Geschwindigkeit (km/h)", "#9467bd"),
)
"""Panels top to bottom; a panel is skipped if its column is all null."""


def _panel_trace(spec: _PanelSpec, series: pl.DataFrame) -> go.Scatter:
    """Build one panel's line, or filled-area, trace.

    Args:
        spec: The panel to build a trace for.
        series: A time series built by :func:`plots.series.build_time_series`.

    Returns:
        A scatter trace plotting ``spec.column`` against elapsed time.

    >>> series = pl.DataFrame(
    ...     {"elapsed_s": [0.0, 1.0], "altitude_m": [10.0, 12.0], "power": [200, 210]}
    ... )
    >>> trace = _panel_trace(_PANELS[0], series)
    >>> trace.fill
    'tozeroy'
    >>> power_spec = _PanelSpec("power", "Leistung (W)", "#d62728")
    >>> _panel_trace(power_spec, series).fill is None
    True
    """
    return go.Scatter(
        x=series["elapsed_s"],
        y=series[spec.column],
        mode="lines",
        name=spec.title,
        line={"color": spec.color},
        fill="tozeroy" if spec.fill else None,
    )


def build_timeline_figure(series: pl.DataFrame) -> go.Figure:
    """Build the workout timeline figure from the available panels.

    Args:
        series: A time series built by
            :func:`plots.series.build_time_series`.

    Returns:
        A plotly figure with one row per available panel, in the fixed
        order altitude, power, heart rate, speed; x-axes are coupled so
        zooming or panning any panel moves all of them together.

    Raises:
        AnalysisError: If none of the panel columns carry any data.

    >>> from datetime import UTC, datetime, timedelta
    >>> from models import RecordPoint
    >>> from plots.series import build_time_series
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [
    ...     RecordPoint(timestamp=start, power=200, heart_rate=140),
    ...     RecordPoint(
    ...         timestamp=start + timedelta(seconds=1), power=210, heart_rate=141
    ...     ),
    ... ]
    >>> fig = build_timeline_figure(build_time_series(records))
    >>> len(fig.data)
    2
    """
    channels = available_channels(series)
    panels = [spec for spec in _PANELS if spec.column in channels]
    if not panels:
        raise AnalysisError("no chartable channel available for the timeline")

    fig = make_subplots(
        rows=len(panels),
        cols=1,
        shared_xaxes=True,
        subplot_titles=[spec.title for spec in panels],
    )
    for row, spec in enumerate(panels, start=1):
        fig.add_trace(_panel_trace(spec, series), row=row, col=1)
    return fig
