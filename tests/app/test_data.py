"""Tests for app.data."""

from datetime import timedelta
from pathlib import Path

from app.data import (
    WorkoutUploadDetails,
    import_recovery_days,
    import_workouts,
    save_and_load_workouts,
)
from models import PlannedIntervalSpec, WorkoutCategory
from storage.schema import init_db

VALID_FIT = Path("data/beispiel/training_gueltig.fit")
BROKEN_FIT = Path("data/beispiel/training_defekt.fit")
EMPTY_FIT = Path("data/beispiel/training_leer.fit")

VALID_CSV = Path("data/beispiel/physiologische_zyklen_gueltig.csv")
BROKEN_CSV = Path("data/beispiel/physiologische_zyklen_defekt.csv")
EMPTY_CSV = Path("data/beispiel/physiologische_zyklen_leer.csv")


def test_import_workouts_imports_valid_fixture() -> None:
    imports, failures = import_workouts([VALID_FIT])

    assert failures == []
    assert len(imports) == 1
    assert imports[0].filename == "training_gueltig.fit"
    assert imports[0].workout.sport == "cycling"


def test_import_workouts_reports_broken_fixture_as_failure_not_exception() -> None:
    imports, failures = import_workouts([BROKEN_FIT])

    assert imports == []
    assert len(failures) == 1
    assert failures[0].filename == "training_defekt.fit"


def test_import_workouts_reports_empty_fixture_as_failure() -> None:
    imports, failures = import_workouts([EMPTY_FIT])

    assert imports == []
    assert len(failures) == 1


def test_import_workouts_keeps_valid_files_independent_of_broken_ones() -> None:
    imports, failures = import_workouts([VALID_FIT, BROKEN_FIT])

    assert len(imports) == 1
    assert len(failures) == 1


def test_import_workouts_handles_empty_selection() -> None:
    assert import_workouts([]) == ([], [])


def test_import_workouts_leaves_name_unset_without_one_given() -> None:
    imports, _ = import_workouts([VALID_FIT])

    assert imports[0].workout.name is None


def test_import_workouts_applies_a_given_name() -> None:
    imports, _ = import_workouts(
        [VALID_FIT], [WorkoutUploadDetails(name="Feierabendrunde")]
    )

    assert imports[0].workout.name == "Feierabendrunde"


def test_import_workouts_matches_details_to_files_by_position() -> None:
    imports, _ = import_workouts(
        [VALID_FIT, BROKEN_FIT],
        [
            WorkoutUploadDetails(name="Meine Runde"),
            WorkoutUploadDetails(name="Kaputte Datei"),
        ],
    )

    assert len(imports) == 1
    assert imports[0].workout.name == "Meine Runde"


def test_import_workouts_leaves_category_unset_without_one_given() -> None:
    imports, _ = import_workouts([VALID_FIT])

    assert imports[0].workout.category is None


def test_import_workouts_applies_a_given_category() -> None:
    imports, _ = import_workouts(
        [VALID_FIT], [WorkoutUploadDetails(category=WorkoutCategory.RECOVERY)]
    )

    assert imports[0].workout.category is WorkoutCategory.RECOVERY


def test_import_workouts_applies_a_given_planned_interval_spec() -> None:
    plan = PlannedIntervalSpec(
        repetitions=6, duration=timedelta(minutes=4), target_power_w=280
    )

    imports, _ = import_workouts(
        [VALID_FIT],
        [
            WorkoutUploadDetails(
                category=WorkoutCategory.INTERVALLE, planned_intervals=plan
            )
        ],
    )

    assert imports[0].workout.planned_intervals == plan


def test_import_recovery_days_returns_nothing_without_a_file() -> None:
    assert import_recovery_days(None) == ([], None, None)


def test_import_recovery_days_imports_valid_fixture() -> None:
    days, report, failure = import_recovery_days(VALID_CSV)

    assert failure is None
    assert report is not None
    assert len(days) == 10


def test_import_recovery_days_reports_broken_fixture_as_failure_not_exception() -> None:
    days, report, failure = import_recovery_days(BROKEN_CSV)

    assert days == []
    assert report is None
    assert failure is not None
    assert failure.filename == "physiologische_zyklen_defekt.csv"


def test_import_recovery_days_reports_empty_fixture_as_failure() -> None:
    days, report, failure = import_recovery_days(EMPTY_CSV)

    assert days == []
    assert report is None
    assert failure is not None


def test_save_and_load_workouts_roundtrips_a_new_upload() -> None:
    conn = init_db(":memory:")
    imports, _ = import_workouts([VALID_FIT])

    loaded, duplicates = save_and_load_workouts(conn, imports)

    assert len(loaded) == 1
    assert loaded[0].sport == "cycling"
    assert duplicates == []


def test_save_and_load_workouts_skips_a_reupload_of_the_same_file() -> None:
    conn = init_db(":memory:")
    imports, _ = import_workouts([VALID_FIT])
    save_and_load_workouts(conn, imports)

    loaded_again, _ = save_and_load_workouts(conn, imports)

    assert len(loaded_again) == 1


def test_save_and_load_workouts_reports_a_reupload_as_a_duplicate() -> None:
    conn = init_db(":memory:")
    imports, _ = import_workouts([VALID_FIT])
    save_and_load_workouts(conn, imports)

    _, duplicates = save_and_load_workouts(conn, imports)

    assert len(duplicates) == 1
    assert duplicates[0].filename == "training_gueltig.fit"


def test_save_and_load_workouts_returns_earlier_saves_without_new_uploads() -> None:
    """A fresh browser session with nothing uploaded yet must still see
    what was saved in an earlier session — that's the point of persisting."""
    conn = init_db(":memory:")
    imports, _ = import_workouts([VALID_FIT])
    save_and_load_workouts(conn, imports)

    loaded, duplicates = save_and_load_workouts(conn, [])

    assert len(loaded) == 1
    assert duplicates == []
