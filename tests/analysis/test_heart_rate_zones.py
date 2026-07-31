"""Tests for analysis.heart_rate_zones."""

from datetime import UTC, datetime, timedelta

import deal
import pytest

from analysis.heart_rate_zones import _hr_zone, heart_rate_zone_distribution
from models import RecordPoint

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _records_with_heart_rate(*heart_rates: int, gap_s: int = 1) -> list[RecordPoint]:
    return [
        RecordPoint(timestamp=START + timedelta(seconds=i * gap_s), heart_rate=hr)
        for i, hr in enumerate(heart_rates)
    ]


class TestHrZone:
    @pytest.mark.parametrize(
        ("hr_reserve", "expected_zone"),
        [
            (-0.1, 1),
            (0.0, 1),
            (0.59, 1),
            (0.60, 2),
            (0.69, 2),
            (0.70, 3),
            (0.79, 3),
            (0.80, 4),
            (0.89, 4),
            (0.90, 5),
            (1.0, 5),
            (1.2, 5),
        ],
    )
    def test_classifies_hr_reserve_into_the_right_zone(
        self, hr_reserve: float, expected_zone: int
    ) -> None:
        assert _hr_zone(hr_reserve) == expected_zone


class TestHeartRateZoneDistribution:
    def test_all_time_falls_into_a_single_steady_zone(self) -> None:
        # hr_rest=50, hr_max=200 -> HRR range 150; HR=125 -> (125-50)/150 = 50%: zone 1
        records = _records_with_heart_rate(*([125] * 10))

        zones = heart_rate_zone_distribution(records, hr_rest=50, hr_max=200)

        assert zones is not None
        assert zones.zone_1 == timedelta(seconds=9)
        assert zones.zone_2 == timedelta(0)
        assert zones.zone_5 == timedelta(0)

    def test_splits_time_across_zones_as_heart_rate_rises(self) -> None:
        # HR=100 -> HRR 33% -> zone 1; HR=180 -> HRR 87% -> zone 4
        records = _records_with_heart_rate(100, 180, 180)

        zones = heart_rate_zone_distribution(records, hr_rest=50, hr_max=200)

        assert zones is not None
        assert zones.zone_1 == timedelta(seconds=1)
        assert zones.zone_4 == timedelta(seconds=1)

    def test_excludes_a_paused_gap_from_every_zone(self) -> None:
        """A 64s auto-pause must not be counted as 64s in any zone."""
        records = _records_with_heart_rate(125, 125, gap_s=64)

        zones = heart_rate_zone_distribution(records, hr_rest=50, hr_max=200)

        assert zones is not None
        assert zones.zone_1 == timedelta(0)

    def test_zone_durations_never_exceed_the_recorded_span(self) -> None:
        records = _records_with_heart_rate(*([125] * 60))

        zones = heart_rate_zone_distribution(records, hr_rest=50, hr_max=200)

        assert zones is not None
        total = zones.zone_1 + zones.zone_2 + zones.zone_3 + zones.zone_4 + zones.zone_5
        span = records[-1].timestamp - records[0].timestamp
        assert total <= span

    def test_none_without_hr_rest_or_hr_max(self) -> None:
        records = _records_with_heart_rate(120, 130)

        assert heart_rate_zone_distribution(records, hr_rest=None, hr_max=200) is None
        assert heart_rate_zone_distribution(records, hr_rest=50, hr_max=None) is None

    def test_none_without_any_heart_rate_data(self) -> None:
        records = [
            RecordPoint(timestamp=START + timedelta(seconds=i), power=150)
            for i in range(10)
        ]

        assert heart_rate_zone_distribution(records, hr_rest=50, hr_max=200) is None

    def test_none_for_a_single_heart_rate_sample(self) -> None:
        records = _records_with_heart_rate(140)

        assert heart_rate_zone_distribution(records, hr_rest=50, hr_max=200) is None

    def test_rejects_hr_rest_not_below_hr_max(self) -> None:
        records = _records_with_heart_rate(140, 150)

        with pytest.raises(deal.PreContractError):
            heart_rate_zone_distribution(records, hr_rest=200, hr_max=200)
