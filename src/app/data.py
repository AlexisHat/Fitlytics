"""Import uploaded FIT and Whoop CSV files into validated, session-ready data.

Kept free of any ``streamlit`` import so it stays unit-testable like the rest
of the codebase: a Streamlit ``UploadedFile`` and a plain ``Path`` are both
just an ``IO[bytes]``/``Path`` source to the readers underneath.
"""

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import IO, NamedTuple

from errors import DataValidationError, FileImportError
from models import RecoveryDay, Workout
from readers.fit import import_fit_file
from readers.whoop import import_whoop_csv
from storage.workouts import load_workouts, save_workout
from validation.recovery import validate_recovery_days
from validation.report import ValidationReport
from validation.workout import validate_workout

UploadSource = Path | IO[bytes]
"""A single uploaded file: a filesystem path in tests, or the file-like
object Streamlit's ``st.file_uploader()`` returns at runtime."""


class ImportFailure(NamedTuple):
    """One file that could not be imported.

    Attributes:
        filename: Name of the file that failed, as shown by the uploader.
        message: Human-readable reason, from the raised FitlyticsError.
    """

    filename: str
    message: str


class WorkoutImport(NamedTuple):
    """One successfully imported and validated workout.

    Attributes:
        filename: Name of the source file, as shown by the uploader.
        workout: The validated workout.
        report: What validation discarded from it, if anything.
    """

    filename: str
    workout: Workout
    report: ValidationReport


def import_workouts(
    files: Sequence[UploadSource],
    names: Sequence[str | None] | None = None,
) -> tuple[list[WorkoutImport], list[ImportFailure]]:
    """Import and validate every uploaded FIT file, skipping unusable ones.

    A single broken or empty file must not block the others: each file is
    imported independently, and a failure is reported back rather than
    raised, so the calling UI never has to catch an exception itself.

    Args:
        files: Uploaded FIT files, e.g. from
            ``st.file_uploader(accept_multiple_files=True)``.
        names: An optional title for each file, in the same order as
            ``files``; a None entry leaves the workout's own name unset, so
            it falls back to :attr:`models.Workout.display_name`. Defaults
            to no title for any file.

    Returns:
        The successfully imported workouts and the failures, both in the
        order ``files`` was given.
    """
    resolved_names = names if names is not None else [None] * len(files)
    imports: list[WorkoutImport] = []
    failures: list[ImportFailure] = []
    for file, name in zip(files, resolved_names, strict=True):
        try:
            workout, report = validate_workout(import_fit_file(file))
        except (FileImportError, DataValidationError) as exc:
            failures.append(ImportFailure(file.name, str(exc)))
            continue
        if name is not None:
            workout = workout.model_copy(update={"name": name})
        imports.append(WorkoutImport(file.name, workout, report))
    return imports, failures


def save_and_load_workouts(
    conn: sqlite3.Connection, workout_imports: Sequence[WorkoutImport]
) -> tuple[list[Workout], list[WorkoutImport]]:
    """Persist this rerun's newly imported workouts and return every saved one.

    Once a workout has been uploaded and saved, the database becomes the
    single source of truth for what the calendar shows: a workout stays
    visible without re-uploading it in a later session, and re-uploading
    the same file again is a no-op (``save_workout`` skips it by
    start_time) — reported back as a duplicate rather than silently
    dropped, so the UI can tell the athlete nothing new happened.

    Args:
        conn: An open connection with the schema already created (see
            :func:`storage.schema.init_db`).
        workout_imports: This rerun's freshly imported and validated
            workouts.

    Returns:
        Every workout ever saved, sorted by start_time; and the subset of
        ``workout_imports`` that were already saved before this call (same
        start_time) and so were skipped.

    Raises:
        StorageError: If saving or loading fails.
    """
    duplicates = [
        imported
        for imported in workout_imports
        if not save_workout(conn, imported.workout)
    ]
    return load_workouts(conn), duplicates


def import_recovery_days(
    file: UploadSource | None,
) -> tuple[list[RecoveryDay], ValidationReport | None, ImportFailure | None]:
    """Import and validate the uploaded Whoop CSV, if any.

    Args:
        file: The uploaded Whoop CSV, e.g. from ``st.file_uploader()``, or
            None if nothing was uploaded yet.

    Returns:
        The validated recovery days (empty if ``file`` is None), the
        validation report, and an import failure — of the latter two,
        exactly one is set once ``file`` is not None.
    """
    if file is None:
        return [], None, None

    try:
        days = import_whoop_csv(file)
    except FileImportError as exc:
        return [], None, ImportFailure(file.name, str(exc))

    try:
        cleaned, report = validate_recovery_days(days)
    except DataValidationError as exc:
        return [], None, ImportFailure(file.name, str(exc))

    return cleaned, report, None
