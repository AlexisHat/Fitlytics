"""Streamlit entry point: sidebar data upload and session-wide settings.

Run with ``uv run streamlit run src/app/main.py``. Uploaded workouts and the
FTP/heart-rate profile are saved to a local SQLite database (see
``storage``) and reloaded on every run, so they stay available without
re-entering them in a later session. Recovery days and interval results are
not persisted (see ``docs/entscheidungen.md``, Meilenstein 10).
"""

from pathlib import Path
from typing import Final

import streamlit as st

from analysis.calendar import CalendarDay
from app.calendar_view import render_calendar
from app.data import (
    WorkoutImport,
    import_recovery_days,
    import_workouts,
    save_and_load_workouts,
)
from app.day_view import render_day
from errors import StorageError
from models import Workout
from storage import init_db
from storage.profile import load_profile, save_profile

_DB_PATH: Final = Path("data/private/fitlytics.db")


def _optional_sidebar_number(label: str, default: int | None = None) -> int | None:
    """Render a sidebar number input where 0 means "unknown", not a literal 0.

    Args:
        label: Field label shown to the user.
        default: Value to pre-fill the field with (e.g. a previously saved
            profile value), or None to start at "unknown".

    Returns:
        The entered value, or None if left at 0.
    """
    value = st.sidebar.number_input(label, min_value=0, value=default or 0, step=1)
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


def _load_persisted_workouts(workout_imports: list[WorkoutImport]) -> list[Workout]:
    """Save this rerun's new uploads to SQLite and return every saved workout.

    Falls back to just this rerun's uploads, with an error shown, if the
    database itself is unavailable (e.g. an unwritable disk) — a storage
    problem must not crash the app, only mean uploads won't outlive this
    session.

    Args:
        workout_imports: This rerun's freshly imported and validated
            workouts.

    Returns:
        Every workout ever saved, or just this rerun's uploads if
        persistence failed.
    """
    try:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = init_db(_DB_PATH)
        try:
            return save_and_load_workouts(conn, workout_imports)
        finally:
            conn.close()
    except (StorageError, OSError) as exc:
        st.error(f"Speicherung nicht verfügbar, gilt nur für diese Sitzung: {exc}")
        return [imported.workout for imported in workout_imports]


def _load_stored_profile() -> tuple[int | None, int | None, int | None]:
    """Load the athlete's previously saved FTP/heart-rate profile, if any.

    Falls back to nothing saved, with an error shown, if the database is
    unavailable — matches :func:`_load_persisted_workouts`.

    Returns:
        ``(ftp_watts, hr_rest, hr_max)`` as last saved, or all None if
        nothing was saved yet or the database is unavailable.
    """
    try:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = init_db(_DB_PATH)
        try:
            return load_profile(conn)
        finally:
            conn.close()
    except (StorageError, OSError) as exc:
        st.error(f"Profil konnte nicht geladen werden: {exc}")
        return None, None, None


def _persist_profile(
    ftp_watts: int | None, hr_rest: int | None, hr_max: int | None
) -> None:
    """Save the sidebar's current profile fields so they survive the session.

    Saves exactly what was entered, even a momentarily invalid
    hr_rest/hr_max combination — :func:`_validated_hr_profile` only decides
    what this rerun's calculations may use, it must not cause a typo to
    silently wipe an already-saved, valid profile. Falls back to a
    session-only profile, with an error shown, if the database is
    unavailable — matches :func:`_load_persisted_workouts`.

    Args:
        ftp_watts: The athlete's Functional Threshold Power, as entered.
        hr_rest: The athlete's resting heart rate, as entered.
        hr_max: The athlete's maximum heart rate, as entered.
    """
    try:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = init_db(_DB_PATH)
        try:
            save_profile(conn, ftp_watts, hr_rest, hr_max)
        finally:
            conn.close()
    except (StorageError, OSError) as exc:
        st.error(
            f"Profil konnte nicht gespeichert werden, gilt nur für diese Sitzung: {exc}"
        )


def _render_sidebar() -> None:
    """Render the sidebar's uploaders and settings, importing into session_state."""
    st.sidebar.header("Daten hochladen")
    fit_files = st.sidebar.file_uploader(
        "FIT-Dateien (Trainings)", type="fit", accept_multiple_files=True
    )
    csv_file = st.sidebar.file_uploader("Whoop-CSV (Recovery)", type="csv")

    workout_imports, workout_failures = import_workouts(fit_files or [])
    recovery_days, recovery_report, recovery_failure = import_recovery_days(csv_file)

    st.session_state.workouts = _load_persisted_workouts(workout_imports)
    st.session_state.workout_imports = workout_imports
    st.session_state.workout_failures = workout_failures
    st.session_state.recovery_days = recovery_days
    st.session_state.recovery_report = recovery_report
    st.session_state.recovery_failure = recovery_failure

    st.sidebar.header("Einstellungen")
    stored_ftp, stored_hr_rest, stored_hr_max = _load_stored_profile()
    ftp_watts = _optional_sidebar_number("FTP (Watt)", stored_ftp)
    hr_rest = _optional_sidebar_number("Ruhepuls (bpm)", stored_hr_rest)
    hr_max = _optional_sidebar_number("Maximalpuls (bpm)", stored_hr_max)
    _persist_profile(ftp_watts, hr_rest, hr_max)

    st.session_state.ftp_watts = ftp_watts
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
    """Render the detail view for the day selected on the calendar, if any.

    Args:
        calendar_days: The currently rendered calendar days.
    """
    selected = st.session_state.get("selected_date")
    if selected is None:
        return

    day = next((day for day in calendar_days if day.date == selected), None)
    if day is None:
        return

    render_day(
        day,
        tuple(st.session_state.recovery_days),
        st.session_state.ftp_watts,
        st.session_state.hr_rest,
        st.session_state.hr_max,
    )


def main() -> None:
    """Render the Fitlytics Streamlit app."""
    st.set_page_config(page_title="Fitlytics", layout="wide")
    st.title("Fitlytics")
    _render_sidebar()
    _render_import_log()

    calendar_days = render_calendar(
        st.session_state.workouts,
        st.session_state.ftp_watts,
        st.session_state.hr_rest,
        st.session_state.hr_max,
    )
    _render_selected_day(calendar_days)


if __name__ == "__main__":
    main()
