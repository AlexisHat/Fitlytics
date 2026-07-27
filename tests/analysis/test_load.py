"""Tests for analysis.load."""

from datetime import UTC, datetime, timedelta

import deal
import pytest
from hypothesis import given
from hypothesis import strategies as st

from analysis.load import (
    intensity_factor,
    normalized_power,
    training_stress_score,
    trimp,
    variability_index,
)
from models import RecordPoint

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _records_with_power(*powers: int, gap_s: int = 1) -> list[RecordPoint]:
    return [
        RecordPoint(timestamp=START + timedelta(seconds=i * gap_s), power=power)
        for i, power in enumerate(powers)
    ]


def _records_with_heart_rate(*heart_rates: int, gap_s: int = 1) -> list[RecordPoint]:
    return [
        RecordPoint(timestamp=START + timedelta(seconds=i * gap_s), heart_rate=hr)
        for i, hr in enumerate(heart_rates)
    ]


class TestNormalizedPower:
    def test_constant_power_equals_that_power(self) -> None:
        records = _records_with_power(*([200] * 30))

        assert normalized_power(records) == 200.0

    def test_rewards_surges_over_a_steady_effort_of_the_same_average(self) -> None:
        steady = _records_with_power(*([200] * 40))
        surging = _records_with_power(*([100] * 20 + [300] * 20))

        np_steady = normalized_power(steady)
        np_surging = normalized_power(surging)

        assert np_steady is not None
        assert np_surging is not None
        assert np_surging > np_steady

    def test_none_below_the_30_sample_window(self) -> None:
        assert normalized_power(_records_with_power(*([200] * 29))) is None

    def test_none_without_any_power_data(self) -> None:
        assert normalized_power(_records_with_heart_rate(*([140] * 40))) is None

    def test_none_for_a_very_short_workout(self) -> None:
        assert normalized_power(_records_with_power(150, 160)) is None


class TestIntensityFactor:
    def test_divides_normalized_power_by_ftp(self) -> None:
        assert intensity_factor(210.0, 210) == 1.0

    def test_none_without_normalized_power(self) -> None:
        assert intensity_factor(None, 210) is None

    def test_none_without_ftp(self) -> None:
        assert intensity_factor(182.0, None) is None

    def test_rejects_non_positive_ftp(self) -> None:
        with pytest.raises(deal.PreContractError):
            intensity_factor(182.0, 0)


class TestTrainingStressScore:
    def test_one_hour_exactly_at_ftp_scores_100(self) -> None:
        tss = training_stress_score(
            normalized_power=210.0,
            intensity_factor=1.0,
            moving_time=timedelta(hours=1),
            ftp_watts=210,
        )

        assert tss == 100.0

    def test_none_without_intensity_factor(self) -> None:
        tss = training_stress_score(210.0, None, timedelta(hours=1), 210)

        assert tss is None

    def test_rejects_non_positive_ftp(self) -> None:
        with pytest.raises(deal.PreContractError):
            training_stress_score(210.0, 1.0, timedelta(hours=1), -210)


class TestVariabilityIndex:
    def test_equals_one_for_a_perfectly_steady_effort(self) -> None:
        assert variability_index(200.0, 200.0) == 1.0

    def test_none_without_avg_power(self) -> None:
        assert variability_index(200.0, None) is None

    def test_none_when_avg_power_is_zero(self) -> None:
        """A fully coasting workout has no meaningful power ratio."""
        assert variability_index(0.0, 0.0) is None


class TestTrimp:
    def test_none_without_hr_rest_or_hr_max(self) -> None:
        records = _records_with_heart_rate(140, 150)

        assert trimp(records, hr_rest=None, hr_max=190) is None
        assert trimp(records, hr_rest=50, hr_max=None) is None

    def test_none_without_any_heart_rate_data(self) -> None:
        records = _records_with_power(150, 160)

        assert trimp(records, hr_rest=50, hr_max=190) is None

    def test_none_for_a_single_heart_rate_sample(self) -> None:
        """A single sample has no interval to weight by duration."""
        records = _records_with_heart_rate(140)

        assert trimp(records, hr_rest=50, hr_max=190) is None

    def test_is_positive_for_an_elevated_heart_rate(self) -> None:
        records = _records_with_heart_rate(*([140] * 60))

        result = trimp(records, hr_rest=50, hr_max=190)

        assert result is not None
        assert result > 0

    def test_higher_heart_rate_yields_higher_trimp(self) -> None:
        easy = _records_with_heart_rate(*([120] * 60))
        hard = _records_with_heart_rate(*([170] * 60))

        trimp_easy = trimp(easy, hr_rest=50, hr_max=190)
        trimp_hard = trimp(hard, hr_rest=50, hr_max=190)

        assert trimp_easy is not None
        assert trimp_hard is not None
        assert trimp_hard > trimp_easy

    def test_excludes_a_paused_gap_from_the_impulse(self) -> None:
        """A 64s auto-pause contributes no training impulse at all."""
        paused = _records_with_heart_rate(140, 140, gap_s=64)

        assert trimp(paused, hr_rest=50, hr_max=190) == 0.0

    def test_a_normal_gap_contributes_impulse(self) -> None:
        continuous = _records_with_heart_rate(140, 140, gap_s=1)

        result = trimp(continuous, hr_rest=50, hr_max=190)

        assert result is not None
        assert result > 0.0

    def test_rejects_hr_rest_not_below_hr_max(self) -> None:
        records = _records_with_heart_rate(140, 150)

        with pytest.raises(deal.PreContractError):
            trimp(records, hr_rest=190, hr_max=190)


@given(
    power=st.integers(min_value=0, max_value=2000),
    n=st.integers(min_value=30, max_value=200),
)
def test_normalized_power_of_constant_power_equals_that_power(
    power: int, n: int
) -> None:
    records = _records_with_power(*([power] * n))

    assert normalized_power(records) == pytest.approx(float(power))
