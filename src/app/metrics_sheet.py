"""The full metric sheet for one workout, opened from the day view.

The day view's tiles carry the four figures that answer "what was this
ride". Everything else Fitlytics computes — the Coggan load metrics, TRIMP,
the efficiency pair, the climbing figures — lives one click away here, so
the day stays readable without those numbers going unused.
"""

import streamlit as st
from pydantic import BaseModel

from analysis.efficiency import decoupling_pct, efficiency_factor
from analysis.ftp import effective_ftp
from analysis.load import (
    intensity_factor,
    normalized_power,
    training_stress_score,
    trimp,
    variability_index,
)
from analysis.workout import WorkoutMetrics, compute_workout_metrics
from app.formatting import format_optional
from models import Workout

_MS_TO_KMH = 3.6
"""Metres per second to kilometres per hour; the models store speed in m/s
and only the display converts it (see ``plots.series``)."""


class WorkoutMetricSheet(BaseModel):
    """Every figure Fitlytics computes for a single workout.

    The summary metrics plus the derived ones that need an athlete profile
    to scale against. A figure is None whenever its inputs were missing —
    a ride without a power meter has no Normalized Power, and one without a
    known FTP has no TSS — which is an ordinary state, not an error.

    Attributes:
        metrics: The workout's summary metrics.
        ftp_watts: The FTP the power-based figures were scaled to, or None
            if neither the workout nor the profile knows one.
        normalized_power_w: Normalized Power in watts, or None.
        intensity_factor: Normalized Power relative to FTP, or None.
        training_stress_score: Coggan's TSS, or None.
        variability_index: Normalized Power over average power, or None.
        trimp: Banister's Training Impulse, or None if no heart-rate
            profile is known.
        efficiency_factor: Power per heartbeat, or None.
        decoupling_pct: Aerobic decoupling in percent, or None.
    """

    metrics: WorkoutMetrics
    ftp_watts: int | None
    normalized_power_w: float | None
    intensity_factor: float | None
    training_stress_score: float | None
    variability_index: float | None
    trimp: float | None
    efficiency_factor: float | None
    decoupling_pct: float | None


def build_metric_sheet(
    workout: Workout,
    profile_ftp: int | None,
    hr_rest: int | None,
    hr_max: int | None,
) -> WorkoutMetricSheet:
    """Compute every figure available for one workout.

    The FTP is resolved the same way the interval analysis resolves it (see
    :func:`analysis.ftp.effective_ftp`): the workout's own value wins, so a
    ride keeps the numbers it was recorded against even after the athlete
    retests.

    Args:
        workout: The workout to summarise.
        profile_ftp: The athlete's current FTP from the sidebar, or None.
        hr_rest: The athlete's resting heart rate, or None if unknown; must
            be lower than hr_max if both are given.
        hr_max: The athlete's maximum heart rate, or None if unknown.

    Returns:
        The workout's full metric sheet.

    >>> from datetime import UTC, datetime, timedelta
    >>> from models import RecordPoint
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> workout = Workout(
    ...     start_time=start,
    ...     sport="cycling",
    ...     records=[
    ...         RecordPoint(
    ...             timestamp=start + timedelta(seconds=i),
    ...             power=200,
    ...             heart_rate=150,
    ...         )
    ...         for i in range(2)
    ...     ],
    ... )
    >>> sheet = build_metric_sheet(workout, 250, hr_rest=50, hr_max=190)
    >>> sheet.ftp_watts
    250

    Two records are too few for Normalized Power's 30-sample window, so
    everything built on it stays None rather than being approximated:

    >>> sheet.normalized_power_w is None, sheet.training_stress_score is None
    (True, True)

    The efficiency factor falls back to average power and is available:

    >>> round(sheet.efficiency_factor, 3)
    1.333
    """
    metrics = compute_workout_metrics(workout)
    ftp_watts = effective_ftp(workout, profile_ftp)

    power = normalized_power(workout.records)
    factor = intensity_factor(power, ftp_watts)

    return WorkoutMetricSheet(
        metrics=metrics,
        ftp_watts=ftp_watts,
        normalized_power_w=power,
        intensity_factor=factor,
        training_stress_score=training_stress_score(
            power, factor, metrics.moving_time, ftp_watts
        ),
        variability_index=variability_index(power, metrics.avg_power),
        trimp=trimp(workout.records, hr_rest, hr_max),
        efficiency_factor=efficiency_factor(
            power, metrics.avg_power, metrics.avg_heart_rate
        ),
        decoupling_pct=decoupling_pct(workout.records),
    )


def _to_kmh(speed_ms: float | None) -> float | None:
    """Convert a speed from metres per second to kilometres per hour.

    Args:
        speed_ms: The speed in m/s, or None if none was recorded.

    Returns:
        The speed in km/h, or None.

    >>> _to_kmh(10.0)
    36.0
    >>> _to_kmh(None) is None
    True
    """
    return None if speed_ms is None else speed_ms * _MS_TO_KMH


def _render_duration_section(metrics: WorkoutMetrics) -> None:
    """Show the ride's duration, distance and speed figures."""
    st.markdown("**Dauer und Strecke**")
    columns = st.columns(4)
    columns[0].metric(
        "Dauer (gesamt)",
        str(metrics.elapsed_time),
        help="Vom ersten bis zum letzten Messpunkt, inklusive Pausen.",
    )
    columns[1].metric(
        "Dauer (bewegt)",
        str(metrics.moving_time),
        help="Gesamtdauer abzüglich aller Aufzeichnungslücken über 2 Sekunden.",
    )
    columns[2].metric(
        "Ø Geschwindigkeit",
        format_optional(_to_kmh(metrics.avg_speed_ms), "{:.1f} km/h"),
    )
    columns[3].metric(
        "Max. Geschwindigkeit",
        format_optional(_to_kmh(metrics.max_speed_ms), "{:.1f} km/h"),
    )


def _render_power_section(sheet: WorkoutMetricSheet) -> None:
    """Show the power-based load metrics, all scaled to the workout's FTP."""
    st.markdown("**Leistung und Belastung**")
    columns = st.columns(4)
    columns[0].metric(
        "Normalized Power",
        format_optional(sheet.normalized_power_w, "{:.0f} W"),
        help="Die 30-Sekunden-Rollleistung, mit der vierten Potenz gewichtet: "
        "bewertet Antritte höher als eine gleichmäßige Fahrt gleichen Schnitts.",
    )
    columns[1].metric(
        "Intensity Factor",
        format_optional(sheet.intensity_factor, "{:.2f}"),
        help="Normalized Power geteilt durch FTP. 1,00 heißt: die ganze Fahrt "
        "lag im Schnitt an der Schwelle.",
    )
    columns[2].metric(
        "TSS",
        format_optional(sheet.training_stress_score, "{:.0f}"),
        help="Training Stress Score. Eine Stunde exakt an der FTP ergibt 100.",
    )
    columns[3].metric(
        "Variability Index",
        format_optional(sheet.variability_index, "{:.2f}"),
        help="Normalized Power geteilt durch Ø-Leistung. Nahe 1,0 ist gleichmäßig; "
        "höhere Werte bedeuten viele Antritte.",
    )

    if sheet.metrics.work_kj is not None:
        st.metric(
            "Arbeit",
            format_optional(sheet.metrics.work_kj, "{:.0f} kJ"),
            help="Gesamte mechanische Arbeit, bevorzugt der Gerätewert.",
        )


def _render_heart_rate_section(sheet: WorkoutMetricSheet) -> None:
    """Show the heart-rate figures and the two efficiency metrics."""
    st.markdown("**Herzfrequenz und Effizienz**")
    columns = st.columns(4)
    columns[0].metric(
        "Max. Herzfrequenz", format_optional(sheet.metrics.max_heart_rate, "{:.0f} bpm")
    )
    columns[1].metric(
        "TRIMP",
        format_optional(sheet.trimp, "{:.0f}"),
        help="Training Impulse nach Banister: gewichtet jede Minute exponentiell "
        "nach der genutzten Herzfrequenzreserve.",
    )
    columns[2].metric(
        "Efficiency Factor",
        format_optional(sheet.efficiency_factor, "{:.2f}"),
        help="Leistung pro Herzschlag. Steigt der Wert über Wochen bei ähnlichen "
        "Fahrten, verbessert sich die Grundlagenausdauer.",
    )
    columns[3].metric(
        "Decoupling",
        format_optional(sheet.decoupling_pct, "{:+.1f} %"),
        help="Drift des Verhältnisses Watt/Puls von der ersten zur zweiten "
        "Fahrthälfte. Nahe 0 % heißt gleichmäßig durchgehalten.",
    )


def _render_terrain_section(metrics: WorkoutMetrics) -> None:
    """Show the climbing and cadence figures."""
    st.markdown("**Höhenmeter und Trittfrequenz**")
    columns = st.columns(4)
    columns[0].metric(
        "Höhenmeter", format_optional(metrics.elevation_gain_m, "{:.0f} m")
    )
    columns[1].metric(
        "VAM",
        format_optional(metrics.vam, "{:.0f} m/h"),
        help="Höhenmeter pro Stunde Bewegungszeit, über die ganze Fahrt gerechnet "
        "statt je Anstieg.",
    )
    columns[2].metric(
        "Ø Trittfrequenz", format_optional(metrics.avg_cadence, "{:.0f} rpm")
    )
    columns[3].metric(
        "Max. Trittfrequenz", format_optional(metrics.max_cadence, "{:.0f} rpm")
    )


@st.dialog("Alle Kennzahlen", width="large")
def _show_metric_sheet_dialog(sheet: WorkoutMetricSheet, title: str) -> None:
    """Open the modal showing every computed figure for one workout.

    A modal rather than another section in the day view: these are figures
    the athlete looks up now and then, not ones they scroll past on every
    visit, and closing the modal puts the day back exactly as it was — the
    same reason the interval close-up is one (see
    :mod:`app.interval_detail`).

    Args:
        sheet: The workout's computed figures.
        title: The workout's display name, as the modal's heading.
    """
    st.markdown(f"**{title}**")
    if sheet.ftp_watts is None:
        st.caption(
            "Ohne FTP-Wert in der Seitenleiste lassen sich Intensity Factor "
            "und TSS nicht berechnen."
        )
    else:
        st.caption(f"Leistungswerte skaliert auf {sheet.ftp_watts} W FTP.")

    _render_duration_section(sheet.metrics)
    _render_power_section(sheet)
    _render_heart_rate_section(sheet)
    _render_terrain_section(sheet.metrics)


def render_metric_sheet_button(
    workout: Workout,
    profile_ftp: int | None,
    hr_rest: int | None,
    hr_max: int | None,
) -> None:
    """Render the button that opens the workout's full metric sheet.

    Args:
        workout: The workout being shown.
        profile_ftp: The athlete's current FTP from the sidebar, or None.
        hr_rest: The athlete's resting heart rate, or None if unknown; must
            be lower than hr_max if both are given.
        hr_max: The athlete's maximum heart rate, or None if unknown.
    """
    if st.button(
        "Mehr Kennzahlen ansehen",
        key=f"metric_sheet_{workout.start_time.isoformat()}",
    ):
        sheet = build_metric_sheet(workout, profile_ftp, hr_rest, hr_max)
        _show_metric_sheet_dialog(sheet, workout.display_name)
