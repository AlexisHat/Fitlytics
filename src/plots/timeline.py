"""Panel-driven multi-panel figure for a single workout's time series."""

from collections.abc import Sequence
from typing import Any, Final, NamedTuple

import plotly.graph_objects as go
import polars as pl

from errors import AnalysisError
from plots.distance import prepare_distance_axis
from plots.series import available_channels, trim_to_first_fully_measured_row

_TOP_MARGIN: Final = 0.04
"""Fraction of the plot area reserved above the topmost panel."""

_BOTTOM_MARGIN: Final = 0.14
"""Fraction of the plot area reserved below the bottom panel for its
x-axis' tick labels, title and — when the bottom panel is elevation — the
rangeslider (see :func:`build_timeline_figure`)."""

_PANEL_GAP: Final = 0.055
"""Vertical gap between stacked panels; also where that panel's title sits."""

_BASE_HEIGHT_PX: Final = 130
"""Fixed figure height budget in pixels for margins and the x-axis."""

_PANEL_HEIGHT_PX: Final = 155
"""Height budget in pixels per panel. Plotly's default figure height stays
fixed regardless of panel count, so without scaling it explicitly, the
fixed-size title annotations start overlapping their neighbours as more
panels are added and each panel's share of that fixed height shrinks."""

_RANGESLIDER_EXTRA_HEIGHT_PX: Final = 90
"""Extra height budget when the elevation panel's rangeslider is shown —
it is drawn below the plotting area plotly's own domain math accounts for,
not inside it, so the figure needs the room added explicitly."""

_RANGESLIDER_THICKNESS: Final = 0.08
"""The navigator strip's share of the plotting area's height, per
requirement: a thin overview, not another full panel."""

_RAW_TRACE_OPACITY: Final = 0.35
"""Opacity of a panel's faint, unsmoothed background line."""

_X_AXIS_TITLE: Final = "Distanz (km)"
_X_TICKFORMAT: Final = ",.1f"
_X_HOVERFORMAT: Final = ".2f"
_X_TICKSUFFIX: Final = " km"


class _PanelSpec(NamedTuple):
    """One panel's data column, label and line styling.

    Attributes:
        column: Column of the time series this panel's main line plots.
        title: Panel title, used as both the panel heading and the
            trace name.
        color: Line (and, if filled, fill) colour as a hex string.
        fill: Whether to fill the area under the line down to the axis
            baseline, e.g. for a terrain-profile look. Always positive
            here — elevation is plotted as an absolute height above sea
            level, never relative to the start, so the fill never dips
            below the baseline into a second colour.
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
    _PanelSpec("power_rolling_30s", "Leistung (W)", "#c1440e", height_weight=1.2),
    _PanelSpec("heart_rate", "Herzfrequenz (bpm)", "#2ca02c", height_weight=1.2),
    _PanelSpec("speed_kmh", "Geschwindigkeit (km/h)", "#9467bd", hover_format=".1f"),
    _PanelSpec(
        "altitude_smoothed_m", "Höhe (m)", "#a0785a", fill=True, height_weight=0.7
    ),
)
"""Panels top to bottom; a panel is skipped if its underlying measured
channel (see :data:`_DERIVED_FROM`) is all null. Elevation is always last:
when present, it is pulled onto its own rangeslider-carrying axis (see
:func:`build_timeline_figure`), and being at the bottom of the stack keeps
its position the same whether or not that split happens."""

_ELEVATION_COLUMN: Final = "altitude_smoothed_m"

_DERIVED_FROM: Final[dict[str, str]] = {
    "power_rolling_30s": "power",
    "altitude_smoothed_m": "altitude_m",
}
"""Maps a panel's displayed column to the measured channel it is derived
from — a panel is only chartable if that underlying measurement exists,
regardless of what :func:`available_channels` says about the derived
column itself (which it never measured directly)."""

_SHOW_RAW_BACKGROUND: Final[frozenset[str]] = frozenset({"power_rolling_30s"})
"""Panels whose measured source (see :data:`_DERIVED_FROM`) is additionally
drawn as a faint background line behind the main one, e.g. raw power behind
its smoothed mean. That raw line never appears in the elevation navigator —
the navigator only ever carries the one trace assigned to its own axis
(see :func:`build_timeline_figure`), and power is never that trace."""


def _panel_y_domains(weights: Sequence[float]) -> list[tuple[float, float]]:
    """Compute each panel's vertical slice of the plot area, top to bottom.

    Args:
        weights: One relative height per panel, top to bottom, e.g. from
            :attr:`_PanelSpec.height_weight`; must be non-empty and
            positive.

    Returns:
        One ``(low, high)`` domain per panel, top to bottom, sized
        proportionally to its weight and leaving room above the first
        panel and below the last one.

    >>> _panel_y_domains([1.0, 1.0])
    [(0.5775, 0.96), (0.14, 0.5225)]
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
    spec: _PanelSpec,
    series: pl.DataFrame,
    x: pl.Series,
    xaxis: str,
    yaxis: str,
    *,
    include_elapsed_time: bool = False,
) -> go.Scatter:
    """Build one panel's main line, or filled-area, trace.

    Args:
        spec: The panel to build a trace for.
        series: A time series built by :func:`plots.series.build_time_series`
            and cleaned by :func:`plots.distance.prepare_distance_axis`.
        x: The shared distance axis, from ``series["distance_km"]``.
        xaxis: The plotly x-axis id this panel is drawn on, e.g. ``"x2"``.
        yaxis: The plotly y-axis id this panel is drawn on, e.g. ``"y3"``.
        include_elapsed_time: Whether to add an extra "Zeit: HH:MM:SS" line
            to this trace's hover label. Exactly one trace per unified-hover
            group needs this — attaching it to every trace in the group
            would repeat the same line once per panel; see
            :func:`build_timeline_figure`.

    Returns:
        A scatter trace plotting ``spec.column`` against ``x``. A panel
        listed in :data:`_SHOW_RAW_BACKGROUND` carries no hover label of
        its own — the exact, unsmoothed reading is more useful to point at
        than the smoothed one, so :func:`_raw_background_trace` answers
        hover for that panel instead, even though this smoothed line is
        what stays visible on top.

    >>> series = pl.DataFrame(
    ...     {
    ...         "distance_km": [0.0, 0.5],
    ...         "altitude_smoothed_m": [100.0, 102.0],
    ...         "heart_rate": [140, 141],
    ...         "elapsed_hms": ["00:00:00", "00:00:05"],
    ...     }
    ... )
    >>> x = series["distance_km"]
    >>> trace = _panel_trace(_PANELS[3], series, x, "x2", "y4")
    >>> trace.fill
    'tozeroy'
    >>> hr_spec = _PanelSpec("heart_rate", "Herzfrequenz (bpm)", "#2ca02c")
    >>> _panel_trace(hr_spec, series, x, "x", "y2").fill is None
    True
    """
    has_raw_counterpart = spec.column in _SHOW_RAW_BACKGROUND
    time_suffix = "<br>Zeit: %{customdata}" if include_elapsed_time else ""
    return go.Scatter(
        x=x,
        y=series[spec.column],
        xaxis=xaxis,
        yaxis=yaxis,
        mode="lines",
        name=spec.title,
        line={"color": spec.color},
        fill="tozeroy" if spec.fill else None,
        customdata=series["elapsed_hms"] if include_elapsed_time else None,
        hoverinfo="skip" if has_raw_counterpart else None,
        hovertemplate=(
            None
            if has_raw_counterpart
            else f"{spec.title}: %{{y:{spec.hover_format}}}{time_suffix}<extra></extra>"
        ),
    )


def _raw_background_trace(
    spec: _PanelSpec,
    raw_column: str,
    series: pl.DataFrame,
    x: pl.Series,
    yaxis: str,
    *,
    include_elapsed_time: bool = False,
) -> go.Scatter:
    """Build a panel's faint, unsmoothed line, drawn behind its main one.

    Still thin and semi-transparent so the smoothed line on top stays the
    visually dominant one, but this raw trace is what answers hover for the
    panel — the exact reading at that instant, matching the one point on
    the chart the cursor is actually nearest to, rather than a 30s average.
    Always on the shared "x" axis: only the power panel has a raw
    counterpart, and power always belongs to the group of panels sharing
    that axis (see :func:`build_timeline_figure`).

    Args:
        spec: The panel to build the raw trace for.
        raw_column: Column of the unsmoothed value, from :data:`_DERIVED_FROM`.
        series: A time series built by :func:`plots.series.build_time_series`.
        x: The shared distance axis, from ``series["distance_km"]``.
        yaxis: The plotly y-axis id this panel is drawn on, e.g. ``"y2"``.
        include_elapsed_time: Whether to add an extra "Zeit: HH:MM:SS" line
            to this trace's hover label; see :func:`_panel_trace`.

    Returns:
        A thin, semi-transparent scatter trace plotting ``raw_column``,
        with a German hover label formatted per ``spec.hover_format`` but
        excluded from the legend.

    >>> series = pl.DataFrame(
    ...     {
    ...         "distance_km": [0.0, 0.1],
    ...         "power": [200, 210],
    ...         "elapsed_hms": ["00:00:00", "00:00:05"],
    ...     }
    ... )
    >>> x = series["distance_km"]
    >>> power_spec = _PanelSpec("power_rolling_30s", "Leistung (W)", "#c1440e")
    >>> trace = _raw_background_trace(power_spec, "power", series, x, "y2")
    >>> trace.opacity, trace.showlegend
    (0.35, False)
    >>> trace.hovertemplate
    'Leistung (W): %{y:.0f}<extra></extra>'
    """
    time_suffix = "<br>Zeit: %{customdata}" if include_elapsed_time else ""
    return go.Scatter(
        x=x,
        y=series[raw_column],
        xaxis="x",
        yaxis=yaxis,
        mode="lines",
        name=spec.title,
        line={"color": spec.color, "width": 1},
        opacity=_RAW_TRACE_OPACITY,
        customdata=series["elapsed_hms"] if include_elapsed_time else None,
        hovertemplate=(
            f"{spec.title}: %{{y:{spec.hover_format}}}{time_suffix}<extra></extra>"
        ),
        showlegend=False,
    )


def _x_axis_layout(**overrides: Any) -> dict[str, Any]:
    """Shared distance-axis formatting, as a base dict further layout merges into.

    Args:
        **overrides: Additional or overriding layout keys, e.g. ``anchor``
            or ``rangeslider``.

    Returns:
        A plotly x-axis layout dict.
    """
    return {
        "type": "linear",
        "tickformat": _X_TICKFORMAT,
        "hoverformat": _X_HOVERFORMAT,
        "ticksuffix": _X_TICKSUFFIX,
        "showspikes": True,
        "spikemode": "across",
        "spikesnap": "cursor",
        "spikethickness": 1,
        **overrides,
    }


def build_timeline_figure(series: pl.DataFrame) -> go.Figure:
    """Build the workout timeline figure from the available panels.

    The x-axis is always cumulative distance (see
    :func:`plots.distance.prepare_distance_axis`) rather than elapsed time —
    the wall-clock or elapsed reading survives only as an extra line in the
    hover label.

    Every panel except elevation shares one x-axis, so zooming, panning and
    the hover crosshair on any of them move or appear in every one of them
    at once. Elevation sits on a second x-axis instead: it carries the
    figure's rangeslider, an always-full-length overview of the ride with
    the current zoom window marked on it, and the native rangeslider mirrors
    *every* trace on its host axis with no way to exclude one — so elevation
    needs an axis of its own to keep that overview to a single trace. The
    two axes are still kept in lockstep for zooming and panning via
    ``matches``, in both directions: zooming the top panels moves elevation
    and the rangeslider's marked window with them, and dragging the
    rangeslider zooms the top panels the same way a shared axis would have.
    The trade-off is that the crosshair itself does not reach into the
    elevation panel — a separate axis, even a matched one, does not carry
    plotly's spike line across the join (see ``docs/entscheidungen.md``).

    Args:
        series: A time series built by
            :func:`plots.series.build_time_series`.

    Returns:
        A plotly figure with one panel per available channel, in the fixed
        order power, heart rate, speed, elevation. No legend, since every
        panel is already labelled by its own heading. Leading rows before
        every shown panel's channel has a value are dropped, so a slow GPS
        or barometer lock doesn't stagger the start.

    Raises:
        AnalysisError: If none of the panel columns carry any data, or if
            the workout has neither a distance channel nor enough speed
            data to derive one (see
            :func:`plots.distance.prepare_distance_axis`).

    >>> from datetime import UTC, datetime, timedelta
    >>> from models import RecordPoint
    >>> from plots.series import build_time_series
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [
    ...     RecordPoint(
    ...         timestamp=start + timedelta(seconds=i),
    ...         power=200,
    ...         heart_rate=140,
    ...         distance_m=float(i * 5),
    ...     )
    ...     for i in range(2)
    ... ]
    >>> fig = build_timeline_figure(build_time_series(records))
    >>> len(fig.data)
    3
    """
    channels = available_channels(series)
    panels = [
        spec
        for spec in _PANELS
        if _DERIVED_FROM.get(spec.column, spec.column) in channels
    ]
    if not panels:
        raise AnalysisError("no chartable channel available for the timeline")

    required_columns = {_DERIVED_FROM.get(spec.column, spec.column) for spec in panels}
    series = prepare_distance_axis(series)
    series = trim_to_first_fully_measured_row(series, sorted(required_columns))

    has_elevation = panels[-1].column == _ELEVATION_COLUMN
    top_panels = panels[:-1] if has_elevation else panels
    elevation_panel = panels[-1] if has_elevation else None

    x = series["distance_km"]
    domains = _panel_y_domains([spec.height_weight for spec in panels])
    top_domains = domains[: len(top_panels)]

    fig = go.Figure()
    layout: dict[str, Any] = {
        "template": "plotly_white",
        "showlegend": False,
        "hovermode": "x unified",
        "annotations": [],
    }

    top_bottom_yaxis = "y" if len(top_panels) <= 1 else f"y{len(top_panels)}"
    layout["xaxis"] = _x_axis_layout(
        anchor=top_bottom_yaxis,
        title={"text": _X_AXIS_TITLE} if not has_elevation else None,
        showticklabels=not has_elevation,
    )

    for i, (spec, (low, high)) in enumerate(zip(top_panels, top_domains, strict=True)):
        yaxis_id = "y" if i == 0 else f"y{i + 1}"
        axis_key = "yaxis" if i == 0 else f"yaxis{i + 1}"
        layout[axis_key] = {"domain": [low, high], "anchor": "x", "showspikes": True}
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
        include_time = i == 0
        if spec.column in _SHOW_RAW_BACKGROUND:
            raw_column = _DERIVED_FROM[spec.column]
            fig.add_trace(
                _raw_background_trace(
                    spec,
                    raw_column,
                    series,
                    x,
                    yaxis_id,
                    include_elapsed_time=include_time,
                )
            )
            include_time = False
        fig.add_trace(
            _panel_trace(
                spec, series, x, "x", yaxis_id, include_elapsed_time=include_time
            )
        )

    height = _BASE_HEIGHT_PX + _PANEL_HEIGHT_PX * len(panels)

    if elevation_panel is not None:
        elevation_yaxis_id = "y" if not top_panels else f"y{len(top_panels) + 1}"
        elevation_yaxis_key = (
            "yaxis" if not top_panels else f"yaxis{len(top_panels) + 1}"
        )
        elevation_low, elevation_high = domains[-1]
        layout["xaxis2"] = _x_axis_layout(
            anchor=elevation_yaxis_id,
            matches="x",
            title={"text": _X_AXIS_TITLE},
            rangeslider={
                "visible": True,
                "thickness": _RANGESLIDER_THICKNESS,
                "bgcolor": "#f5f5f5",
            },
        )
        layout[elevation_yaxis_key] = {
            "domain": [elevation_low, elevation_high],
            "anchor": "x2",
            "showspikes": True,
        }
        layout["annotations"].append(
            {
                "text": elevation_panel.title,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": elevation_high + _PANEL_GAP / 2,
                "showarrow": False,
                "font": {"size": 16},
            }
        )
        fig.add_trace(
            _panel_trace(
                elevation_panel,
                series,
                x,
                "x2",
                elevation_yaxis_id,
                include_elapsed_time=True,
            )
        )
        height += _RANGESLIDER_EXTRA_HEIGHT_PX

    layout["height"] = height
    fig.update_layout(layout)
    return fig
