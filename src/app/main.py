"""Streamlit entry point: sidebar data upload and session-wide settings.

Run with ``uv run streamlit run src/app/main.py``. There is no persistence
yet (SQLite storage is a later milestone), so all imported data lives only
in ``st.session_state`` for the duration of the browser session.
"""

import streamlit as st

from analysis.calendar import CalendarDay, build_calendar
from app.calendar_view import render_calendar
from app.data import import_recovery_days, import_workouts


def _optional_sidebar_number(label: str) -> int | None:
    """Render a sidebar number input where 0 means "unknown", not a literal 0.

    Args:
        label: Field label shown to the user.

    Returns:
        The entered value, or None if left at 0.
    """
    value = st.sidebar.number_input(label, min_value=0, value=0, step=1)
    return int(value) or None


def _validated_hr_profile(
    hr_rest: int | None, hr_max: int | None
) -> tuple[int | None, int | None]:
    """Guard against an invalid resting/maximum heart rate combination.

    Downstream calculations (training load, heart-rate zones) require
    hr_rest < hr_max as a contract precondition — a real invariant for
    internal callers, but these two values come straight from sidebar
    input here, so a typo must not reach them as a contract violation.

    Args:
        hr_rest: The entered resting heart rate, or None.
        hr_max: The entered maximum heart rate, or None.

    Returns:
        ``(hr_rest, hr_max)`` unchanged, or ``(None, None)`` with an error
        shown in the sidebar if both are set but hr_rest is not below
        hr_max.
    """
    if hr_rest is not None and hr_max is not None and hr_rest >= hr_max:
        st.sidebar.error("Ruhepuls muss unter dem Maximalpuls liegen.")
        return None, None
    return hr_rest, hr_max


def _render_sidebar() -> None:
    """Render the sidebar's uploaders and settings, importing into session_state."""
    st.sidebar.header("Daten hochladen")
    fit_files = st.sidebar.file_uploader(
        "FIT-Dateien (Trainings)", type="fit", accept_multiple_files=True
    )
    csv_file = st.sidebar.file_uploader("Whoop-CSV (Recovery)", type="csv")

    workout_imports, workout_failures = import_workouts(fit_files or [])
    recovery_days, recovery_report, recovery_failure = import_recovery_days(csv_file)

    st.session_state.workouts = [imported.workout for imported in workout_imports]
    st.session_state.workout_imports = workout_imports
    st.session_state.workout_failures = workout_failures
    st.session_state.recovery_days = recovery_days
    st.session_state.recovery_report = recovery_report
    st.session_state.recovery_failure = recovery_failure

    st.sidebar.header("Einstellungen")
    st.session_state.ftp_watts = _optional_sidebar_number("FTP (Watt)")
    hr_rest = _optional_sidebar_number("Ruhepuls (bpm)")
    hr_max = _optional_sidebar_number("Maximalpuls (bpm)")
    st.session_state.hr_rest, st.session_state.hr_max = _validated_hr_profile(
        hr_rest, hr_max
    )


def _render_import_log() -> None:
    """Show import failures and a summary of what was successfully imported."""
    for failure in st.session_state.workout_failures:
        st.error(f"{failure.filename}: {failure.message}")
    if st.session_state.recovery_failure is not None:
        failure = st.session_state.recovery_failure
        st.error(f"{failure.filename}: {failure.message}")

    if not st.session_state.workouts and not st.session_state.recovery_days:
        st.info("Noch keine Daten hochgeladen.")
        return

    st.write(
        f"{len(st.session_state.workouts)} Workout(s), "
        f"{len(st.session_state.recovery_days)} Recovery-Tag(e) importiert."
    )
    with st.expander("Import-Details"):
        for imported in st.session_state.workout_imports:
            st.write(f"**{imported.filename}** — {imported.report.summary()}")
        if st.session_state.recovery_report is not None:
            st.write(f"**Whoop-CSV** — {st.session_state.recovery_report.summary()}")


def _render_selected_day(calendar_days: tuple[CalendarDay, ...]) -> None:
    """Show a minimal summary of the selected day's workouts.

    Full metrics, plots and interval analysis follow in a later milestone;
    this only surfaces that a day was picked, to make the calendar's
    click-to-select wiring visible end to end.

    Args:
        calendar_days: The currently rendered calendar days.
    """
    selected = st.session_state.get("selected_date")
    if selected is None:
        return

    day = next((day for day in calendar_days if day.date == selected), None)
    if day is None:
        return

    st.subheader(selected.isoformat())
    if not day.workouts:
        st.write("Ruhetag.")
        return
    for workout in day.workouts:
        st.write(f"- {workout.sport} ab {workout.start_time.isoformat()}")


def main() -> None:
    """Render the Fitlytics Streamlit app."""
    st.set_page_config(page_title="Fitlytics", layout="wide")
    st.title("Fitlytics")
    _render_sidebar()
    _render_import_log()

    calendar_days = build_calendar(
        st.session_state.workouts,
        st.session_state.ftp_watts,
        st.session_state.hr_rest,
        st.session_state.hr_max,
    )
    render_calendar(calendar_days)
    _render_selected_day(calendar_days)


if __name__ == "__main__":
    main()
