"""Tests for app.metrics_sheet."""

from datetime import UTC, datetime, timedelta

from app.metrics_sheet import _to_kmh, build_metric_sheet
from models import RecordPoint, Workout

_START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _ride(
    seconds: int = 60,
    power: int | None = 200,
    heart_rate: int | None = 150,
    ftp_watts: int | None = None,
    total_ascent_m: float | None = None,
    total_descent_m: float | None = None,
) -> Workout:
    records = [
        RecordPoint(
            timestamp=_START + timedelta(seconds=i),
            power=power,
            heart_rate=heart_rate,
            cadence=90,
            speed_ms=10.0,
            distance_m=float(i * 10),
        )
        for i in range(seconds)
    ]
    return Workout(
        start_time=_START,
        sport="cycling",
        records=records,
        ftp_watts=ftp_watts,
        total_ascent_m=total_ascent_m,
        total_descent_m=total_descent_m,
    )


def test_build_metric_sheet_computes_normalized_power_for_a_long_enough_ride() -> None:
    sheet = build_metric_sheet(_ride(), profile_ftp=250, hr_rest=50, hr_max=190)

    assert sheet.normalized_power_w == 200.0


def test_build_metric_sheet_leaves_normalized_power_none_below_the_window() -> None:
    sheet = build_metric_sheet(
        _ride(seconds=29), profile_ftp=250, hr_rest=50, hr_max=190
    )

    assert sheet.normalized_power_w is None


def test_build_metric_sheet_derives_intensity_factor_from_the_ftp() -> None:
    sheet = build_metric_sheet(_ride(), profile_ftp=250, hr_rest=50, hr_max=190)

    assert sheet.intensity_factor == 0.8


def test_build_metric_sheet_prefers_the_workouts_own_ftp_over_the_profile() -> None:
    sheet = build_metric_sheet(
        _ride(ftp_watts=200), profile_ftp=250, hr_rest=50, hr_max=190
    )

    assert sheet.ftp_watts == 200
    assert sheet.intensity_factor == 1.0


def test_build_metric_sheet_falls_back_to_the_profile_ftp() -> None:
    sheet = build_metric_sheet(_ride(), profile_ftp=250, hr_rest=50, hr_max=190)

    assert sheet.ftp_watts == 250


def test_build_metric_sheet_computes_tss_when_an_ftp_is_known() -> None:
    sheet = build_metric_sheet(_ride(), profile_ftp=250, hr_rest=50, hr_max=190)

    assert sheet.training_stress_score is not None
    assert sheet.training_stress_score > 0


def test_build_metric_sheet_leaves_power_figures_none_without_any_ftp() -> None:
    sheet = build_metric_sheet(_ride(), profile_ftp=None, hr_rest=50, hr_max=190)

    assert sheet.ftp_watts is None
    assert sheet.intensity_factor is None
    assert sheet.training_stress_score is None


def test_build_metric_sheet_still_reports_ftp_free_figures_without_an_ftp() -> None:
    sheet = build_metric_sheet(_ride(), profile_ftp=None, hr_rest=50, hr_max=190)

    assert sheet.normalized_power_w == 200.0
    assert sheet.variability_index == 1.0
    assert sheet.trimp is not None


def test_build_metric_sheet_leaves_trimp_none_without_a_heart_rate_profile() -> None:
    sheet = build_metric_sheet(_ride(), profile_ftp=250, hr_rest=None, hr_max=None)

    assert sheet.trimp is None


def test_build_metric_sheet_computes_efficiency_factor() -> None:
    sheet = build_metric_sheet(_ride(), profile_ftp=250, hr_rest=50, hr_max=190)

    assert sheet.efficiency_factor is not None
    assert round(sheet.efficiency_factor, 4) == round(200 / 150, 4)


def test_build_metric_sheet_reports_decoupling_for_a_drifting_ride() -> None:
    heart_rates = [140] * 30 + [160] * 30
    records = [
        RecordPoint(timestamp=_START + timedelta(seconds=i), power=200, heart_rate=hr)
        for i, hr in enumerate(heart_rates)
    ]
    workout = Workout(start_time=_START, sport="cycling", records=records)

    sheet = build_metric_sheet(workout, profile_ftp=250, hr_rest=50, hr_max=190)

    assert sheet.decoupling_pct is not None
    assert round(sheet.decoupling_pct, 2) == 12.5


def test_build_metric_sheet_handles_a_ride_without_a_power_meter() -> None:
    sheet = build_metric_sheet(
        _ride(power=None), profile_ftp=250, hr_rest=50, hr_max=190
    )

    assert sheet.normalized_power_w is None
    assert sheet.training_stress_score is None
    assert sheet.variability_index is None
    assert sheet.metrics.avg_power is None
    assert sheet.trimp is not None


def test_build_metric_sheet_handles_a_ride_without_a_heart_rate_strap() -> None:
    sheet = build_metric_sheet(
        _ride(heart_rate=None), profile_ftp=250, hr_rest=50, hr_max=190
    )

    assert sheet.trimp is None
    assert sheet.efficiency_factor is None
    assert sheet.decoupling_pct is None
    assert sheet.normalized_power_w == 200.0


def test_build_metric_sheet_carries_the_summary_metrics_through() -> None:
    sheet = build_metric_sheet(_ride(), profile_ftp=250, hr_rest=50, hr_max=190)

    assert sheet.metrics.max_heart_rate == 150
    assert sheet.metrics.max_cadence == 90
    assert sheet.metrics.elapsed_time == timedelta(seconds=59)


def test_build_metric_sheet_takes_climbing_figures_from_the_device() -> None:
    sheet = build_metric_sheet(
        _ride(total_ascent_m=500.0, total_descent_m=480.0),
        profile_ftp=250,
        hr_rest=50,
        hr_max=190,
    )

    assert sheet.metrics.elevation_gain_m == 500.0
    assert sheet.metrics.elevation_loss_m == 480.0
    assert sheet.metrics.vam is not None


def test_to_kmh_converts_a_speed() -> None:
    assert _to_kmh(10.0) == 36.0


def test_to_kmh_passes_a_missing_speed_through() -> None:
    assert _to_kmh(None) is None
