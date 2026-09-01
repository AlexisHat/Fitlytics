"""Tests for readers.fit."""

import io
from datetime import UTC, datetime
from pathlib import Path

import pytest

from errors import FileImportError
from readers.fit import _build_record_point, _semicircles_to_degrees, import_fit_file

VALID_FIXTURE = Path("data/beispiel/fixtures/training_gueltig.fit")
EMPTY_FIXTURE = Path("data/beispiel/fixtures/training_leer.fit")
BROKEN_FIXTURE = Path("data/beispiel/fixtures/training_defekt.fit")


def test_import_fit_file_reads_valid_fixture() -> None:
    workout = import_fit_file(VALID_FIXTURE)

    assert workout.sport == "cycling"
    assert workout.sub_sport == "generic"
    assert workout.ftp_watts == 210
    assert workout.start_time == datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC)
    assert len(workout.records) == 20
    assert workout.records[0].heart_rate is None
    assert workout.records[-1].heart_rate == 105
    assert workout.records[-1].power == 26


def test_import_fit_file_reads_device_computed_session_fields() -> None:
    workout = import_fit_file(VALID_FIXTURE)

    assert workout.total_ascent_m == 29
    assert workout.total_descent_m == 29
    assert workout.avg_grade_pct == 0.01
    assert workout.total_work_j == 639616
    assert workout.device_normalized_power == 182
    assert workout.device_intensity_factor == 0.865
    assert workout.device_training_stress_score == 101.7


def test_import_fit_file_accepts_file_like_object() -> None:
    with VALID_FIXTURE.open("rb") as fh:
        workout = import_fit_file(fh)

    assert workout.sport == "cycling"
    assert len(workout.records) == 20


def test_import_fit_file_accepts_bytes_buffer() -> None:
    buffer = io.BytesIO(VALID_FIXTURE.read_bytes())

    workout = import_fit_file(buffer)

    assert len(workout.records) == 20


def test_import_fit_file_rejects_missing_path() -> None:
    with pytest.raises(FileImportError):
        import_fit_file(Path("data/beispiel/fixtures/does_not_exist.fit"))


def test_import_fit_file_rejects_broken_file() -> None:
    with pytest.raises(FileImportError):
        import_fit_file(BROKEN_FIXTURE)


def test_import_fit_file_rejects_empty_file() -> None:
    with pytest.raises(FileImportError):
        import_fit_file(EMPTY_FIXTURE)


def test_build_record_point_maps_optional_fields_to_none_when_absent() -> None:
    timestamp = datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC)

    point = _build_record_point({"timestamp": timestamp})

    assert point.heart_rate is None
    assert point.power is None
    assert point.speed_ms is None


def test_build_record_point_raises_without_timestamp() -> None:
    with pytest.raises(KeyError):
        _build_record_point({"heart_rate": 120})


def test_build_record_point_prefers_enhanced_speed_over_zero_value() -> None:
    timestamp = datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC)
    fields = {"timestamp": timestamp, "enhanced_speed": 0.0, "speed": 5.0}

    point = _build_record_point(fields)

    assert point.speed_ms == 0.0


def test_build_record_point_falls_back_to_plain_speed() -> None:
    timestamp = datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC)
    fields = {"timestamp": timestamp, "speed": 4.0}

    point = _build_record_point(fields)

    assert point.speed_ms == 4.0


def test_build_record_point_falls_back_to_plain_altitude() -> None:
    timestamp = datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC)
    fields = {"timestamp": timestamp, "altitude": 41.0}

    point = _build_record_point(fields)

    assert point.altitude_m == 41.0


def test_build_record_point_converts_position_from_semicircles() -> None:
    timestamp = datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC)
    fields = {
        "timestamp": timestamp,
        "position_lat": 609223111,
        "position_long": 81755779,
    }

    point = _build_record_point(fields)

    assert point.latitude == pytest.approx(51.0645, abs=1e-4)
    assert point.longitude == pytest.approx(6.8527, abs=1e-4)


def test_build_record_point_leaves_position_none_without_gps_fix() -> None:
    timestamp = datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC)

    point = _build_record_point({"timestamp": timestamp})

    assert point.latitude is None
    assert point.longitude is None


def test_semicircles_to_degrees_converts_the_full_range() -> None:
    assert _semicircles_to_degrees(2**31) == pytest.approx(180.0)
    assert _semicircles_to_degrees(-(2**31)) == pytest.approx(-180.0)
    assert _semicircles_to_degrees(0) == 0.0


def test_build_record_point_maps_grade() -> None:
    timestamp = datetime(2026, 7, 16, 14, 11, 39, tzinfo=UTC)
    fields = {"timestamp": timestamp, "grade": -1.23}

    point = _build_record_point(fields)

    assert point.grade_pct == -1.23
