"""Streamlit entry point: sidebar data upload and session-wide settings.

Run with ``uv run streamlit run src/app/main.py``. Uploaded workouts,
recovery days and the FTP/heart-rate profile are saved to a local SQLite
database (see ``storage``) and reloaded on every run, so they stay available
without re-entering them in a later session. Interval results are not
persisted — they are derived from the records and recomputed on demand.
"""

from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Final

import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

from analysis.calendar import CalendarDay
from app.calendar_view import render_calendar
from app.data import (
    WorkoutImport,
    WorkoutUploadDetails,
    import_recovery_days,
    import_workouts,
    save_and_load_recovery_days,
    save_and_load_workouts,
)
from app.day_view import WORKOUT_CATEGORY_LABELS, render_day
from errors import StorageError
from models import PlannedIntervalSpec, RecoveryDay, Workout, WorkoutCategory
from storage import init_db
from storage.profile import load_profile, save_profile
from storage.workouts import load_workouts

_DB_PATH: Final = Path("data/private/fitlytics.db")


def _optional_sidebar_number(
    label: str, default: int | None = None, key: str | None = None
) -> int | None:
    """Render a sidebar number input where 0 means "unknown", not a literal 0.

    Args:
        label: Field label shown to the user.
        default: Value to pre-fill the field with (e.g. a previously saved
            profile value), or None to start at "unknown".
        key: Unique widget key; required when this input is rendered more
            than once per rerun (e.g. once per uploaded file), since
            Streamlit would otherwise collide on the key auto-generated
            from the label alone.

    Returns:
        The entered value, or None if left at 0.
    """
    value = st.sidebar.number_input(
        label, min_value=0, value=default or 0, step=1, key=key
    )
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


def _load_stored_workouts() -> list[Workout]:
    """Load every already-persisted workout, without saving anything new.

    Deliberately read-only: called on every rerun, including the ones
    triggered by typing a title or picking a category, which must not save
    a workout before the athlete has actually confirmed the upload (see
    :func:`_save_workouts`).

    Falls back to an empty list, with an error shown, if the database is
    unavailable.

    Returns:
        Every workout saved so far, or an empty list if the database is
        unavailable or nothing has been saved yet.
    """
    try:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = init_db(_DB_PATH)
        try:
            return load_workouts(conn)
        finally:
            conn.close()
    except (StorageError, OSError) as exc:
        st.error(f"Gespeicherte Workouts konnten nicht geladen werden: {exc}")
        return []


def _store_recovery_days(days: list[RecoveryDay]) -> list[RecoveryDay]:
    """Persist this upload's recovery days and return every stored one.

    Saved without a confirmation step, unlike a workout: a Whoop export
    carries no free-text fields for the athlete to fill in, and an upload
    replaces the days it covers rather than adding to them, so there is
    nothing an early save could get wrong.

    Falls back to just this upload's days, with an error shown, if the
    database is unavailable.

    Args:
        days: This upload's recovery days, empty if nothing was uploaded.

    Returns:
        Every stored recovery day, or just ``days`` if the database is
        unavailable.
    """
    try:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = init_db(_DB_PATH)
        try:
            return save_and_load_recovery_days(conn, days)
        finally:
            conn.close()
    except (StorageError, OSError) as exc:
        st.error(f"Recovery-Daten konnten nicht gespeichert werden: {exc}")
        return days


def _save_workouts(
    workout_imports: list[WorkoutImport],
) -> tuple[list[Workout], list[WorkoutImport]]:
    """Persist the given imports to SQLite and return every saved workout.

    Only called from the sidebar's save button — never automatically on
    upload, so the athlete has a chance to fill in the title, category and
    interval plan before the workout is written to the database.

    Falls back to just these imports, with an error shown, if the database
    itself is unavailable (e.g. an unwritable disk) — a storage problem
    must not crash the app, only mean the save won't outlive this session.

    Args:
        workout_imports: The imports to save, as confirmed by the athlete.

    Returns:
        Every workout ever saved, or just these imports if persistence
        failed; and the subset of ``workout_imports`` that were already
        saved before (same start_time) and so were skipped as duplicates.
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
        return [imported.workout for imported in workout_imports], []


def _load_stored_profile() -> tuple[int | None, int | None, int | None]:
    """Load the athlete's previously saved FTP/heart-rate profile, if any.

    Falls back to nothing saved, with an error shown, if the database is
    unavailable — matches :func:`_load_stored_workouts`.

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
    unavailable — matches :func:`_save_workouts`.

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


def _render_planned_interval_inputs(file_id: str) -> PlannedIntervalSpec | None:
    """Render the plan's repetitions/duration/target-power fields, if any.

    All three are optional and only shown once the athlete has picked the
    Intervalle category for this file; a plan is only built once every one
    of them was actually filled in, matching how the rest of the sidebar
    treats a left-at-zero field as "not given" rather than a real 0.

    Args:
        file_id: The uploaded file's unique id, to key the widgets by.

    Returns:
        The planned interval structure, or None if any field was left blank.
    """
    repetitions = _optional_sidebar_number(
        "Wiederholungen", key=f"workout_interval_reps_{file_id}"
    )
    duration_min = _optional_sidebar_number(
        "Dauer je Intervall (min)", key=f"workout_interval_duration_{file_id}"
    )
    target_power_w = _optional_sidebar_number(
        "Ziel-Leistung (W)", key=f"workout_interval_power_{file_id}"
    )
    if repetitions is None or duration_min is None or target_power_w is None:
        return None
    return PlannedIntervalSpec(
        repetitions=repetitions,
        duration=timedelta(minutes=duration_min),
        target_power_w=target_power_w,
    )


def _render_workout_upload_details(
    files: Sequence[UploadedFile],
) -> list[WorkoutUploadDetails]:
    """Render the title, category and, for Intervalle, plan fields per file.

    Args:
        files: This rerun's uploaded FIT files, in upload order.

    Returns:
        One :class:`~app.data.WorkoutUploadDetails` per file, in the same
        order as ``files``.
    """
    details: list[WorkoutUploadDetails] = []
    for file in files:
        entered_name = st.sidebar.text_input(
            f"Titel für {file.name}",
            key=f"workout_name_{file.file_id}",
            placeholder="optional, sonst „Training am <Datum>“",
        )
        category = st.sidebar.selectbox(
            f"Kategorie für {file.name}",
            options=[None, *WorkoutCategory],
            format_func=lambda c: "–" if c is None else WORKOUT_CATEGORY_LABELS[c],
            key=f"workout_category_{file.file_id}",
        )
        planned_intervals = (
            _render_planned_interval_inputs(file.file_id)
            if category is WorkoutCategory.INTERVALLE
            else None
        )
        details.append(
            WorkoutUploadDetails(
                name=entered_name.strip() or None,
                category=category,
                planned_intervals=planned_intervals,
            )
        )
    return details


def _render_sidebar() -> None:
    """Render the sidebar's uploaders and settings, importing into session_state."""
    st.sidebar.header("Daten hochladen")
    uploader_version = st.session_state.get("fit_uploader_version", 0)
    fit_files = st.sidebar.file_uploader(
        "FIT-Dateien (Trainings)",
        type="fit",
        accept_multiple_files=True,
        key=f"fit_uploader_{uploader_version}",
    )
    workout_upload_details = _render_workout_upload_details(fit_files or [])
    workout_imports, workout_failures = import_workouts(
        fit_files or [], workout_upload_details
    )

    workouts = _load_stored_workouts()
    duplicate_workout_imports: list[WorkoutImport] = []
    if workout_imports:
        save_clicked = st.sidebar.button(
            f"{len(workout_imports)} Workout(s) speichern", type="primary"
        )
        if save_clicked:
            workouts, duplicate_workout_imports = _save_workouts(workout_imports)
            if not duplicate_workout_imports:
                # A clean save: reset the uploader (new widget key) so the
                # sidebar is immediately ready for the next upload instead
                # of still showing the just-saved file.
                st.session_state.fit_uploader_version = uploader_version + 1
                st.rerun()

    csv_file = st.sidebar.file_uploader("Whoop-CSV (Recovery)", type="csv")
    uploaded_recovery, _, recovery_failure = import_recovery_days(csv_file)
    recovery_days = _store_recovery_days(uploaded_recovery)

    st.session_state.workouts = workouts
    st.session_state.workout_imports = workout_imports
    st.session_state.duplicate_workout_imports = duplicate_workout_imports
    st.session_state.workout_failures = workout_failures
    st.session_state.recovery_days = recovery_days
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
    """Show import failures, pending uploads, and a summary of what is saved."""
    for failure in st.session_state.workout_failures:
        st.error(f"{failure.filename}: {failure.message}")
    for duplicate in st.session_state.duplicate_workout_imports:
        start_date = duplicate.workout.start_time.date().isoformat()
        st.warning(
            f"{duplicate.filename}: Workout vom {start_date} ist bereits "
            "gespeichert — übersprungen."
        )
    if st.session_state.recovery_failure is not None:
        failure = st.session_state.recovery_failure
        st.error(f"{failure.filename}: {failure.message}")

    if st.session_state.workout_imports:
        st.info(
            f"{len(st.session_state.workout_imports)} Workout(s) bereit zum "
            "Speichern — Titel/Kategorie in der Sidebar ausfüllen und dort auf "
            "„... speichern“ klicken."
        )

    if (
        not st.session_state.workouts
        and not st.session_state.recovery_days
        and not st.session_state.workout_imports
    ):
        st.info("Noch keine Daten hochgeladen.")
        return

    st.write(
        f"{len(st.session_state.workouts)} Workout(s), "
        f"{len(st.session_state.recovery_days)} Recovery-Tag(e) importiert."
    )


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
