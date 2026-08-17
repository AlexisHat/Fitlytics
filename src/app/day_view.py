"""Render the selected day's detail: metrics, recovery, and every workout plot."""

from collections.abc import Callable
from datetime import date, datetime
from itertools import pairwise
from typing import Final, Literal

import polars as pl
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from analysis.calendar import CalendarDay
from analysis.constants import DEFAULT_POWER_ZONE_MODEL, PowerZoneModel
from analysis.heart_rate_zones import heart_rate_zone_distribution
from analysis.power_zones import power_zone_distribution
from analysis.workout import compute_workout_metrics
from app.formatting import format_interval_type, format_minutes, format_optional
from app.interval_detail import render_interval_buttons
from errors import AnalysisError
from intervals import (
    IntervalBlock,
    IntervalSummary,
    PlanComparison,
    build_interval_blocks,
    classify_block,
    classify_relative_power,
    classify_session,
    compare_to_plan,
    find_candidates,
    mark_standstill,
    resample_to_1hz,
    smooth_power,
    summarize_interval_blocks,
)
from models import (
    PlannedIntervalSpec,
    RecordPoint,
    RecoveryDay,
    Workout,
    WorkoutCategory,
)
from plots import (
    METRICS,
    POWER_ZONE_MODEL_LABELS,
    available_metrics,
    build_gps_map_figure,
    build_time_series,
    build_timeline_figure,
    plot_heart_rate_zones,
    plot_power_with_intervals,
    plot_power_zones,
)

WORKOUT_CATEGORY_LABELS: Final[dict[WorkoutCategory, str]] = {
    WorkoutCategory.GRUNDLAGE: "Grundlage",
    WorkoutCategory.INTERVALLE: "Intervalle",
    WorkoutCategory.GROUPRIDE: "Groupride",
    WorkoutCategory.RECOVERY: "Recovery",
    WorkoutCategory.SONSTIGE: "Sonstige",
}
"""German display label per training category, shared by the upload
selectbox (:mod:`app.main`) and this module's category badge."""

_BadgeColor = Literal[
    "red", "orange", "yellow", "blue", "green", "violet", "gray", "grey", "primary"
]
"""Mirrors ``st.badge``'s own ``color`` parameter type, which streamlit does
not export as a reusable name."""

_WORKOUT_CATEGORY_BADGE_COLORS: Final[dict[WorkoutCategory, _BadgeColor]] = {
    WorkoutCategory.GRUNDLAGE: "blue",
    WorkoutCategory.INTERVALLE: "orange",
    WorkoutCategory.GROUPRIDE: "green",
    WorkoutCategory.RECOVERY: "gray",
    WorkoutCategory.SONSTIGE: "violet",
}
"""Badge colour per category; orange/green match the power/HF panel colours
used elsewhere in the timeline."""


def _select_workout(workouts: tuple[Workout, ...]) -> Workout:
    """Let the user pick a workout when a day has more than one.

    Args:
        workouts: The day's workouts, in recording order; must not be empty.

    Returns:
        The chosen workout — the only one if there is just one.
    """
    if len(workouts) == 1:
        return workouts[0]

    labels = [
        f"{workout.start_time.strftime('%H:%M')} — {workout.display_name}"
        for workout in workouts
    ]
    choice = st.selectbox(
        "Workout", options=range(len(workouts)), format_func=lambda i: labels[i]
    )
    return workouts[choice if choice is not None else 0]


def _render_title(workout: Workout, day_date: date) -> None:
    """Render the workout's title, with its category badge at the right."""
    title_column, tag_column = st.columns([5, 1])
    title_column.subheader(f"{workout.display_name} — {day_date.isoformat()}")
    if workout.category is not None:
        tag_column.badge(
            WORKOUT_CATEGORY_LABELS[workout.category],
            color=_WORKOUT_CATEGORY_BADGE_COLORS[workout.category],
        )


def _render_planned_intervals(workout: Workout) -> None:
    """Show the plan's interval structure as a caption, if one was entered."""
    plan = workout.planned_intervals
    if plan is None:
        return
    minutes = plan.duration.total_seconds() / 60
    st.caption(
        f"Geplant: {plan.repetitions}× {minutes:.0f} min bei {plan.target_power_w} W"
    )


def _render_metrics(workout: Workout) -> None:
    """Render the workout's key summary metrics as a row of tiles."""
    metrics = compute_workout_metrics(workout)
    distance_km = metrics.distance_m / 1000 if metrics.distance_m is not None else None
    columns = st.columns(4)
    columns[0].metric("Dauer (bewegt)", str(metrics.moving_time))
    columns[1].metric(
        "Ø Herzfrequenz", format_optional(metrics.avg_heart_rate, "{:.0f} bpm")
    )
    columns[2].metric("Ø Leistung", format_optional(metrics.avg_power, "{:.0f} W"))
    columns[3].metric("Distanz", format_optional(distance_km, "{:.1f} km"))


def _render_recovery(
    selected_date: date, recovery_days: tuple[RecoveryDay, ...]
) -> None:
    """Show the day's Whoop recovery metrics, if any were imported for it."""
    day = next((entry for entry in recovery_days if entry.date == selected_date), None)
    if day is None:
        return

    st.subheader("Recovery")
    columns = st.columns(3)
    columns[0].metric("Recovery-Score", format_optional(day.recovery_score, "{:.0f} %"))
    columns[1].metric("Ruhepuls", format_optional(day.resting_hr, "{:.0f} bpm"))
    columns[2].metric("HRV", format_optional(day.hrv_ms, "{:.0f} ms"))


def _render_timeline(series: pl.DataFrame) -> None:
    """Render the interactive multi-panel timeline, skipping if unavailable."""
    try:
        figure = build_timeline_figure(series)
    except AnalysisError:
        st.info("Keine Messreihe für die Zeitachsen-Grafik vorhanden.")
        return
    st.plotly_chart(figure, width="stretch")


def _has_power_zone_data(records: list[RecordPoint], ftp_watts: int | None) -> bool:
    """Whether a power-zone chart can be drawn, independent of the chosen model.

    Mirrors the guard inside
    :func:`analysis.power_zones.power_zone_distribution` (FTP known, at
    least two power samples) — the model only changes how those samples are
    bucketed, never whether there is anything to bucket.

    Args:
        records: The workout's record points.
        ftp_watts: The athlete's FTP, or None if unknown.

    Returns:
        True if a power-zone chart can be drawn for this workout.
    """
    if ftp_watts is None:
        return False
    return sum(1 for record in records if record.power is not None) >= 2


def _render_power_zone_plot(
    container: DeltaGenerator, records: list[RecordPoint], ftp_watts: int | None
) -> None:
    """Render the power-zone model picker and the resulting bar chart.

    Assumes :func:`_has_power_zone_data` already confirmed a chart can be
    drawn; still guards the widget's return itself, since Streamlit's
    ``selectbox`` is typed as possibly returning None.
    """
    models = list(PowerZoneModel)
    zone_model = container.selectbox(
        "Leistungszonen-Modell",
        options=models,
        format_func=lambda model: POWER_ZONE_MODEL_LABELS[model],
        index=models.index(DEFAULT_POWER_ZONE_MODEL),
    )
    if zone_model is None:
        return
    distribution = power_zone_distribution(records, ftp_watts, zone_model)
    if distribution is not None:
        container.pyplot(plot_power_zones(distribution))


def _render_zones(
    records: list[RecordPoint],
    hr_rest: int | None,
    hr_max: int | None,
    ftp_watts: int | None,
) -> None:
    """Render HF- and power-zone bar charts, side by side if both are known.

    Falls back to a single full-width chart instead of leaving an empty
    column when only one of the two is available.
    """
    hr_distribution = heart_rate_zone_distribution(records, hr_rest, hr_max)
    has_power_zones = _has_power_zone_data(records, ftp_watts)
    if hr_distribution is None and not has_power_zones:
        return

    st.subheader("Zonen")
    if hr_distribution is not None and has_power_zones:
        hr_column, power_column = st.columns(2)
        hr_column.pyplot(plot_heart_rate_zones(hr_distribution))
        _render_power_zone_plot(power_column, records, ftp_watts)
    elif hr_distribution is not None:
        st.pyplot(plot_heart_rate_zones(hr_distribution))
    else:
        _render_power_zone_plot(st.container(), records, ftp_watts)


def _render_gps_map(workout: Workout, series: pl.DataFrame) -> None:
    """Render the GPS track map with a colour-metric picker, if there is a track."""
    if not workout.has_gps_track:
        return

    metrics = available_metrics(series)
    if not metrics:
        return

    st.subheader("GPS-Karte")
    metric = st.selectbox(
        "Einfärbung", options=metrics, format_func=lambda key: METRICS[key].label
    )
    if metric is None:
        return
    try:
        figure = build_gps_map_figure(series, metric)
    except AnalysisError:
        st.info("Keine Daten für diese Einfärbung.")
        return
    st.plotly_chart(figure, width="stretch")


def _has_strictly_increasing_timestamps(records: list[RecordPoint]) -> bool:
    """Whether ``records`` satisfies the interval pipeline's timing invariant.

    :func:`intervals.resample_to_1hz` requires strictly increasing
    timestamps as a contract precondition — a legitimate invariant for
    internal callers, but ``records`` here comes from a validated,
    real-world FIT file, which only guarantees non-decreasing order. Two
    samples sharing a timestamp is thus a possible real state, not a bug,
    and must not reach that contract as a crash.
    """
    return all(
        earlier.timestamp < later.timestamp for earlier, later in pairwise(records)
    )


def _render_interval_summary(summary: IntervalSummary) -> None:
    """Render the aggregate quality tiles for a workout's interval blocks."""
    columns = st.columns(4)
    columns[0].metric("Anzahl", summary.count)
    columns[1].metric("Ø Gleichmäßigkeit", f"{summary.avg_evenness:.2f}")
    columns[2].metric(
        "Ø Pulsentwicklung",
        format_optional(summary.avg_heart_rate_drift_bpm, "{:+.1f} bpm"),
    )
    columns[3].metric("Watt-Spanne", f"{summary.power_spread_w:.0f} W")


def _render_interval_types(
    blocks: list[IntervalBlock],
    plan: PlannedIntervalSpec | None,
    ftp_watts: int | None,
) -> None:
    """Show the session's training type above the chart, beside the plan's.

    Both sides come from the same bands, so "Geplant: Schwelle · Gefahren:
    Sweet Spot" states plainly that the session landed one band below what
    was intended — the comparison the athlete opens the analysis for.
    """
    ridden = classify_session(blocks)
    if ridden is None or ftp_watts is None:
        st.caption("Für die Typbestimmung fehlt ein FTP-Wert in der Seitenleiste.")
        return

    ridden_label = format_interval_type(ridden)
    if plan is None:
        st.markdown(f"Gefahren: **{ridden_label}**")
        return

    planned = classify_relative_power(plan.target_power_w / ftp_watts)
    st.markdown(
        f"Geplant: **{format_interval_type(planned)}** · Gefahren: **{ridden_label}**"
    )


def _render_interval_table(blocks: list[IntervalBlock]) -> None:
    """Render one row per detected interval block, with the exact numbers."""
    st.dataframe(
        [
            {
                "Start": block.start.strftime("%H:%M:%S"),
                "Dauer": str(block.duration),
                "Typ": format_interval_type(classify_block(block)),
                "Ø Watt": round(block.avg_power_w, 1),
                "Ø Puls": (
                    round(block.avg_heart_rate, 1)
                    if block.avg_heart_rate is not None
                    else None
                ),
                "Pulsentwicklung": (
                    round(block.heart_rate_drift_bpm, 1)
                    if block.heart_rate_drift_bpm is not None
                    else None
                ),
                "Gleichmäßigkeit": round(block.evenness, 2),
            }
            for block in blocks
        ]
    )


def _render_plan_comparison(comparison: PlanComparison) -> None:
    """Render the detected blocks against the plan the athlete entered."""
    st.markdown("**Soll/Ist-Vergleich**")

    columns = st.columns(2)
    columns[0].metric(
        "Wiederholungen",
        f"{comparison.detected_repetitions} von {comparison.planned_repetitions}",
    )
    columns[1].metric(
        "Ø Abweichung Leistung", f"{comparison.mean_power_deviation_w:+.0f} W"
    )

    st.dataframe(
        [
            {
                "Wdh.": number,
                "Dauer": format_minutes(repetition.duration),
                "Δ Dauer": format_minutes(repetition.duration_deviation, signed=True),
                "Ø Watt": round(repetition.avg_power_w),
                "Δ Watt": f"{repetition.power_deviation_w:+.0f}",
            }
            for number, repetition in enumerate(comparison.repetitions, start=1)
        ]
    )


def _run_interval_analysis(workout: Workout, ftp_watts: int | None) -> None:
    """Compute interval-block detection for one workout and render the result."""
    if not _has_strictly_increasing_timestamps(workout.records):
        st.info("Intervallanalyse nicht möglich: doppelte Zeitstempel in den Rohdaten.")
        return

    series = resample_to_1hz(workout.records)
    series = smooth_power(series)
    series = mark_standstill(series)
    candidates = find_candidates(series)
    if not candidates:
        st.info("Keine Intervalle erkannt.")
        return

    blocks = build_interval_blocks(series, candidates, ftp_watts)
    plan = workout.planned_intervals
    target_power_w = plan.target_power_w if plan is not None else None
    _render_interval_types(blocks, plan, ftp_watts)
    st.pyplot(plot_power_with_intervals(series, blocks, target_power_w))
    _render_interval_summary(summarize_interval_blocks(blocks))
    _render_interval_table(blocks)
    render_interval_buttons(
        series, blocks, target_power_w, workout.start_time.isoformat()
    )
    if plan is not None:
        _render_plan_comparison(compare_to_plan(blocks, plan))


def _offers_interval_analysis(workout: Workout) -> bool:
    """Whether interval analysis is offered for this workout at all.

    Only for a session the athlete tagged as intervals. Detection answers
    "which stretches were the hardest", and every ride has some answer to
    that — on an endurance ride it is the climbs, which is true but not
    what the analysis is for. Tying the button to the category keeps the
    feature from making claims the athlete never asked about (see
    ``docs/entscheidungen.md``).

    Args:
        workout: The workout being shown.

    Returns:
        True if the workout is tagged as an interval session.

    >>> from datetime import UTC, datetime
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [RecordPoint(timestamp=start, power=200)]
    >>> ride = Workout(start_time=start, sport="cycling", records=records)
    >>> _offers_interval_analysis(ride)
    False
    >>> session = ride.model_copy(update={"category": WorkoutCategory.INTERVALLE})
    >>> _offers_interval_analysis(session)
    True
    """
    return workout.category is WorkoutCategory.INTERVALLE


def effective_ftp(workout: Workout, profile_ftp: int | None) -> int | None:
    """The FTP a workout's analysis should be scaled to.

    The workout's own value wins, because it belongs to the day the ride
    was recorded: an interval type derived from today's profile FTP would
    silently rewrite itself every time the athlete retests. The profile
    value only fills in for a workout that carries none, e.g. a FIT file
    recorded on a head unit with no FTP configured.

    Args:
        workout: The workout being analysed.
        profile_ftp: The athlete's current FTP from the sidebar, or None.

    Returns:
        The FTP to scale this workout to, or None if neither is known.

    >>> from datetime import UTC, datetime
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [RecordPoint(timestamp=start, power=200)]
    >>> ride = Workout(start_time=start, sport="cycling", records=records)
    >>> effective_ftp(ride.model_copy(update={"ftp_watts": 210}), 223)
    210
    >>> effective_ftp(ride, 223)
    223
    >>> effective_ftp(ride, None)
    """
    return workout.ftp_watts if workout.ftp_watts is not None else profile_ftp


def _render_ftp_input(
    workout: Workout,
    profile_ftp: int | None,
    save_workout_ftp: Callable[[datetime, int | None], None],
) -> int | None:
    """Show the FTP this analysis is scaled to and let the athlete correct it.

    Seeded from :func:`effective_ftp`, so the field starts at the value
    recorded with the ride. A head unit is easily left on a stale FTP after
    a test, which would put every percentage — and with it the interval
    type — off by that much, so the value has to be visible and editable
    right where it is used rather than buried in the profile.

    Args:
        workout: The workout being analysed.
        profile_ftp: The athlete's current FTP from the sidebar, or None.
        save_workout_ftp: Called with the workout's start time and the new
            value whenever the athlete changes it.

    Returns:
        The FTP to scale this analysis to, or None if none is set.
    """
    stored = effective_ftp(workout, profile_ftp)
    entered = st.number_input(
        "FTP dieser Fahrt (Watt)",
        min_value=1,
        max_value=600,
        value=stored,
        step=1,
        key=f"workout_ftp_{workout.start_time.isoformat()}",
        help="Beim Import aus der FIT-Datei übernommen. Korrigieren, wenn der "
        "Radcomputer damals auf einem veralteten Wert stand.",
    )
    if entered != stored:
        save_workout_ftp(workout.start_time, entered)
    return entered


def _render_intervals(
    workout: Workout,
    profile_ftp: int | None,
    save_workout_ftp: Callable[[datetime, int | None], None],
) -> None:
    """Run interval-block detection on demand, behind a per-workout button.

    Offered only where :func:`_offers_interval_analysis` allows it, and
    not run automatically even there: it's a distinct computation the user
    explicitly triggers, not part of the day's baseline view.
    """
    if not _offers_interval_analysis(workout):
        return

    state_key = f"interval_analysis_active_{workout.start_time.isoformat()}"
    button_key = f"interval_button_{workout.start_time.isoformat()}"
    if st.button("Intervallanalyse starten", key=button_key):
        st.session_state[state_key] = True

    if not st.session_state.get(state_key, False):
        return

    st.subheader("Intervalle")
    ftp_watts = _render_ftp_input(workout, profile_ftp, save_workout_ftp)
    _run_interval_analysis(workout, ftp_watts)


def render_day(
    day: CalendarDay,
    recovery_days: tuple[RecoveryDay, ...],
    ftp_watts: int | None,
    hr_rest: int | None,
    hr_max: int | None,
    save_workout_ftp: Callable[[datetime, int | None], None],
) -> None:
    """Render the full detail view for one calendar day: every workout plot.

    Args:
        day: The selected calendar day.
        recovery_days: All imported recovery days, to look the day's own up in.
        ftp_watts: The athlete's current FTP from the sidebar, or None if
            unknown. Only a fallback for a workout that carries none of its
            own — see :func:`effective_ftp`.
        hr_rest: The athlete's resting heart rate, or None if unknown.
        hr_max: The athlete's maximum heart rate, or None if unknown.
        save_workout_ftp: Persists a corrected per-workout FTP. Passed in
            rather than written here so this module stays free of database
            access, like every other view.
    """
    if not day.workouts:
        st.subheader(day.date.isoformat())
        st.write("Ruhetag.")
        _render_recovery(day.date, recovery_days)
        return

    workout = _select_workout(day.workouts)
    _render_title(workout, day.date)
    _render_planned_intervals(workout)
    _render_metrics(workout)
    _render_recovery(day.date, recovery_days)

    series = build_time_series(workout.records)
    _render_timeline(series)
    _render_zones(workout.records, hr_rest, hr_max, ftp_watts)
    _render_gps_map(workout, series)
    _render_intervals(workout, ftp_watts, save_workout_ftp)
