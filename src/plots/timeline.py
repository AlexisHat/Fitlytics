"""Panel-driven multi-panel figure for a single workout's time series."""

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final, NamedTuple

import plotly.graph_objects as go
import polars as pl

from errors import AnalysisError
from plots.series import available_channels


class XAxisMode(StrEnum):
    """Which quantity the timeline figure's shared x-axis plots against.

    Attributes:
        TIME: Elapsed time since the first record, formatted as a clock.
        DISTANCE: Cumulative distance in kilometres.
    """

    TIME = "time"
    DISTANCE = "distance"


_ELAPSED_AXIS_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)
"""Arbitrary anchor for the elapsed-time axis; only the time-of-day part of
the resulting datetimes is ever displayed (via ``%H:%M:%S``), so any date
works as the anchor — plotly only auto-formats axes it recognises as dates,
and there is no separate "duration" axis type to ask for instead."""

_TOP_MARGIN: Final = 0.05
"""Fraction of the plot area reserved above the topmost panel."""

_BOTTOM_MARGIN: Final = 0.12
"""Fraction of the plot area reserved below the bottom panel for the
shared x-axis' tick labels, title and rangeslider."""

_PANEL_GAP: Final = 0.06
"""Vertical gap between stacked panels; also where that panel's title sits."""

_BASE_HEIGHT_PX: Final = 140
"""Fixed figure height budget in pixels for margins, x-axis and rangeslider."""

_PANEL_HEIGHT_PX: Final = 170
"""Height budget in pixels per panel. Plotly's default figure height stays
fixed regardless of panel count, so without scaling it explicitly, the
fixed-size title annotations start overlapping their neighbours as more
panels are added and each panel's share of that fixed height shrinks."""

_RAW_TRACE_OPACITY: Final = 0.35
"""Opacity of a panel's faint, unsmoothed background line."""


class _PanelSpec(NamedTuple):
    """One panel's data column, label and line styling.

    Attributes:
        column: Column of the time series this panel's main line plots.
        title: Panel title, used as both the panel heading and the
            trace name.
        color: Line (and, if filled, fill) colour as a hex string.
        fill: Whether to fill the area under the line down to the axis
            baseline, e.g. for a terrain-profile look.
        hover_format: d3-format spec for this panel's value in the hover
            label, e.g. ``".0f"`` for a whole number.
        height_weight: This panel's share of the stacked panels' height,
            relative to the others (a panel with 2.0 is twice as tall as
            one with 1.0).
    """

    column: str
    title: str
    color: str
    fill: bool = False
    hover_format: str = ".0f"
    height_weight: float = 1.0


_PANELS: Final[tuple[_PanelSpec, ...]] = (
    _PanelSpec("altitude_m", "Höhe (m)", "#a0785a", fill=True, height_weight=0.6),
    _PanelSpec("power_rolling_30s", "Leistung (W)", "#c1440e", height_weight=1.2),
    _PanelSpec("heart_rate", "Herzfrequenz (bpm)", "#2ca02c", height_weight=1.2),
    _PanelSpec("speed_kmh", "Geschwindigkeit (km/h)", "#9467bd", hover_format=".1f"),
)
"""Panels top to bottom; a panel is skipped if its underlying measured
channel (see :data:`_RAW_COLUMNS`) is all null."""

_RAW_COLUMNS: Final[dict[str, str]] = {"power_rolling_30s": "power"}
"""Maps a panel's smoothed column to the raw, measured one drawn faintly
behind it, and doubles as the column :func:`available_channels` is checked
against — a panel showing a rolling mean is only chartable if the raw
measurement behind it exists."""


def _elapsed_time_axis(series: pl.DataFrame) -> pl.Series:
    """Convert ``elapsed_s`` into datetimes plotly can format as a clock time.

    Args:
        series: A time series built by :func:`plots.series.build_time_series`.

    Returns:
        One datetime per row, ``elapsed_s`` seconds after an arbitrary
        epoch; only useful for its ``%H:%M:%S`` formatting on an axis.

    >>> series = pl.DataFrame({"elapsed_s": [0.0, 65.0, 3725.0]})
    >>> _elapsed_time_axis(series).to_list()[1].strftime("%H:%M:%S")
    '00:01:05'
    """
    return series.select(
        (pl.lit(_ELAPSED_AXIS_EPOCH) + pl.duration(seconds=pl.col("elapsed_s"))).alias(
            "x"
        )
    )["x"]


class _XAxisSpec(NamedTuple):
    """Layout for one x-axis display mode.

    Attributes:
        title: German axis title.
        axis_type: Plotly axis type — ``"date"`` for elapsed time (so
            ``%H:%M:%S`` formatting applies), ``"linear"`` for distance.
        tickformat: d3-format (or d3-time-format, for a date axis) spec
            for the tick labels.
        hoverformat: Same, for the unified hover header.
        ticksuffix: Appended to each tick label, e.g. ``" km"``.
    """

    title: str
    axis_type: str
    tickformat: str
    hoverformat: str
    ticksuffix: str = ""


_X_AXIS_SPECS: Final[dict[XAxisMode, _XAxisSpec]] = {
    XAxisMode.TIME: _XAxisSpec("Zeit", "date", "%H:%M:%S", "%H:%M:%S"),
    XAxisMode.DISTANCE: _XAxisSpec("Distanz (km)", "linear", ",.0f", ".2f", " km"),
}


def _x_values(series: pl.DataFrame, x_axis: XAxisMode) -> pl.Series:
    """Get the shared x-axis values for the requested display mode.

    Args:
        series: A time series built by :func:`plots.series.build_time_series`.
        x_axis: Which quantity to plot against.

    Returns:
        Elapsed time as datetimes (see :func:`_elapsed_time_axis`) for
        :attr:`XAxisMode.TIME`, or cumulative distance in km for
        :attr:`XAxisMode.DISTANCE`.

    >>> series = pl.DataFrame({"elapsed_s": [0.0, 1.0], "distance_km": [0.0, 0.01]})
    >>> _x_values(series, XAxisMode.DISTANCE).to_list()
    [0.0, 0.01]
    """
    if x_axis is XAxisMode.DISTANCE:
        return series["distance_km"]
    return _elapsed_time_axis(series)


def _panel_y_domains(weights: Sequence[float]) -> list[tuple[float, float]]:
    """Compute each panel's vertical slice of the plot area, top to bottom.

    All panels are drawn on one shared x-axis rather than the separate,
    merely range-matched ones ``plotly.subplots.make_subplots`` would
    build — only a genuinely shared axis makes plotly draw one spike line
    across every panel on hover, instead of one confined to whichever
    panel the cursor happens to be over.

    Args:
        weights: One relative height per panel, top to bottom, e.g. from
            :attr:`_PanelSpec.height_weight`; must be non-empty and
            positive.

    Returns:
        One ``(low, high)`` domain per panel, top to bottom, sized
        proportionally to its weight and leaving room above for the first
        panel's title and below for the shared x-axis and rangeslider.

    >>> _panel_y_domains([1.0, 1.0])
    [(0.565, 0.95), (0.12, 0.505)]
    """
    top = 1.0 - _TOP_MARGIN
    usable = top - _BOTTOM_MARGIN - _PANEL_GAP * (len(weights) - 1)
    total_weight = sum(weights)
    domains = []
    high = top
    for weight in weights:
        height = usable * (weight / total_weight)
        domains.append((round(high - height, 4), round(high, 4)))
        high -= height + _PANEL_GAP
    return domains


def _panel_trace(
    spec: _PanelSpec, series: pl.DataFrame, x: pl.Series, yaxis: str
) -> go.Scatter:
    """Build one panel's main line, or filled-area, trace.

    Args:
        spec: The panel to build a trace for.
        series: A time series built by :func:`plots.series.build_time_series`.
        x: The shared elapsed-time axis, from :func:`_elapsed_time_axis`.
        yaxis: The plotly y-axis id this panel is drawn on, e.g. ``"y3"``.

    Returns:
        A scatter trace plotting ``spec.column`` against ``x``. A panel
        listed in :data:`_RAW_COLUMNS` carries no hover label of its own —
        the exact, unsmoothed reading is more useful to point at than the
        smoothed one, so :func:`_raw_background_trace` answers hover for
        that panel instead, even though this smoothed line is what stays
        visible on top.

    >>> series = pl.DataFrame(
    ...     {
    ...         "elapsed_s": [0.0, 1.0],
    ...         "altitude_m": [10.0, 12.0],
    ...         "heart_rate": [140, 141],
    ...     }
    ... )
    >>> x = _elapsed_time_axis(series)
    >>> trace = _panel_trace(_PANELS[0], series, x, "y")
    >>> trace.fill
    'tozeroy'
    >>> hr_spec = _PanelSpec("heart_rate", "Herzfrequenz (bpm)", "#2ca02c")
    >>> _panel_trace(hr_spec, series, x, "y2").fill is None
    True
    """
    has_raw_counterpart = spec.column in _RAW_COLUMNS
    return go.Scatter(
        x=x,
        y=series[spec.column],
        xaxis="x",
        yaxis=yaxis,
        mode="lines",
        name=spec.title,
        line={"color": spec.color},
        fill="tozeroy" if spec.fill else None,
        hoverinfo="skip" if has_raw_counterpart else None,
        hovertemplate=(
            None
            if has_raw_counterpart
            else f"{spec.title}: %{{y:{spec.hover_format}}}<extra></extra>"
        ),
    )


def _raw_background_trace(
    spec: _PanelSpec, raw_column: str, series: pl.DataFrame, x: pl.Series, yaxis: str
) -> go.Scatter:
    """Build a panel's faint, unsmoothed line, drawn behind its main one.

    Still thin and semi-transparent so the smoothed line on top stays the
    visually dominant one, but this raw trace is what answers hover for the
    panel — the exact reading at that instant, matching the one point on
    the chart the cursor is actually nearest to, rather than a 30s average.

    Args:
        spec: The panel to build the raw trace for.
        raw_column: Column of the unsmoothed value, from :data:`_RAW_COLUMNS`.
        series: A time series built by :func:`plots.series.build_time_series`.
        x: The shared elapsed-time axis, from :func:`_elapsed_time_axis`.
        yaxis: The plotly y-axis id this panel is drawn on, e.g. ``"y2"``.

    Returns:
        A thin, semi-transparent scatter trace plotting ``raw_column``,
        with a German hover label formatted per ``spec.hover_format`` but
        excluded from the legend.

    >>> series = pl.DataFrame({"elapsed_s": [0.0, 1.0], "power": [200, 210]})
    >>> x = _elapsed_time_axis(series)
    >>> power_spec = _PanelSpec("power_rolling_30s", "Leistung (W)", "#c1440e")
    >>> trace = _raw_background_trace(power_spec, "power", series, x, "y2")
    >>> trace.opacity, trace.showlegend
    (0.35, False)
    >>> trace.hovertemplate
    'Leistung (W): %{y:.0f}<extra></extra>'
    """
    return go.Scatter(
        x=x,
        y=series[raw_column],
        xaxis="x",
        yaxis=yaxis,
        mode="lines",
        name=spec.title,
        line={"color": spec.color, "width": 1},
        opacity=_RAW_TRACE_OPACITY,
        hovertemplate=f"{spec.title}: %{{y:{spec.hover_format}}}<extra></extra>",
        showlegend=False,
    )


def build_timeline_figure(
    series: pl.DataFrame, x_axis: XAxisMode = XAxisMode.TIME
) -> go.Figure:
    """Build the workout timeline figure from the available panels.

    Args:
        series: A time series built by
            :func:`plots.series.build_time_series`.
        x_axis: Whether the shared x-axis plots elapsed time or cumulative
            distance. Defaults to time.

    Returns:
        A plotly figure with one panel per available channel, in the fixed
        order altitude, power, heart rate, speed, all sharing one x-axis:
        zooming, panning and the hover crosshair on any panel move or
        appear in every panel at once, with a rangeslider below the bottom
        one. No legend, since every panel is already labelled by its own
        heading.

    Raises:
        AnalysisError: If none of the panel columns carry any data, or if
            ``x_axis`` is :attr:`XAxisMode.DISTANCE` but the workout has
            no distance channel.

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
    3
    """
    channels = available_channels(series)
    panels = [
        spec
        for spec in _PANELS
        if _RAW_COLUMNS.get(spec.column, spec.column) in channels
    ]
    if not panels:
        raise AnalysisError("no chartable channel available for the timeline")
    if x_axis is XAxisMode.DISTANCE and "distance_km" not in channels:
        raise AnalysisError("distance x-axis requested but no distance was recorded")

    x = _x_values(series, x_axis)
    axis_spec = _X_AXIS_SPECS[x_axis]
    domains = _panel_y_domains([spec.height_weight for spec in panels])
    bottom_yaxis = "y" if len(panels) == 1 else f"y{len(panels)}"

    layout: dict[str, Any] = {
        "template": "plotly_white",
        "showlegend": False,
        "hovermode": "x unified",
        "height": _BASE_HEIGHT_PX + _PANEL_HEIGHT_PX * len(panels),
        "xaxis": {
            "type": axis_spec.axis_type,
            "tickformat": axis_spec.tickformat,
            "hoverformat": axis_spec.hoverformat,
            "ticksuffix": axis_spec.ticksuffix,
            "anchor": bottom_yaxis,
            "showspikes": True,
            "spikemode": "across",
            "spikesnap": "cursor",
            "spikethickness": 1,
            "rangeslider": {"visible": True},
            "title": {"text": axis_spec.title},
        },
        "annotations": [],
    }
    fig = go.Figure()
    for i, (spec, (low, high)) in enumerate(zip(panels, domains, strict=True)):
        yaxis_id = "y" if i == 0 else f"y{i + 1}"
        axis_key = "yaxis" if i == 0 else f"yaxis{i + 1}"
        layout[axis_key] = {
            "domain": [low, high],
            "showspikes": True,
            "spikemode": "toaxis",
            "spikesnap": "cursor",
        }
        layout["annotations"].append(
            {
                "text": spec.title,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": high + _PANEL_GAP / 2,
                "showarrow": False,
                "font": {"size": 16},
            }
        )
        raw_column = _RAW_COLUMNS.get(spec.column)
        if raw_column is not None:
            fig.add_trace(_raw_background_trace(spec, raw_column, series, x, yaxis_id))
        fig.add_trace(_panel_trace(spec, series, x, yaxis_id))

    fig.update_layout(layout)
    return fig
