"""Tests for analysis.power_zones."""

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import deal
import pytest

from analysis.constants import DEFAULT_POWER_ZONE_MODEL, PowerZoneModel
from analysis.power_zones import (
    _ZONE_FRACTIONS,
    _accumulate_zone_durations,
    _scale_to_watts,
    power_zone_distribution,
)
from models import RecordPoint

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _records_with_power(*powers: int | None, gap_s: int = 1) -> list[RecordPoint]:
    return [
        RecordPoint(timestamp=START + timedelta(seconds=i * gap_s), power=power)
        for i, power in enumerate(powers)
    ]


class TestZoneFractionTables:
    @pytest.mark.parametrize(
        ("model", "expected_zone_count"),
        [
            (PowerZoneModel.POLARIZED_3, 3),
            (PowerZoneModel.CLASSIC_5, 5),
            (PowerZoneModel.BRITISH_CYCLING_6, 6),
            (PowerZoneModel.COGGAN_7, 7),
        ],
    )
    def test_each_model_has_its_expected_zone_count(
        self, model: PowerZoneModel, expected_zone_count: int
    ) -> None:
        bounds = _scale_to_watts(200, _ZONE_FRACTIONS[model])

        assert len(bounds) == expected_zone_count
        assert bounds[-1].upper is None

    def test_polarized_three_is_split_at_80_and_100_pct(self) -> None:
        bounds = _scale_to_watts(200, _ZONE_FRACTIONS[PowerZoneModel.POLARIZED_3])

        assert bounds[0].upper == pytest.approx(160.0)
        assert bounds[1].upper == pytest.approx(200.0)

    def test_coggan_seven_is_split_at_published_fractions(self) -> None:
        bounds = _scale_to_watts(200, _ZONE_FRACTIONS[PowerZoneModel.COGGAN_7])

        uppers = [b.upper for b in bounds]
        assert uppers[:-1] == pytest.approx([110.0, 150.0, 180.0, 210.0, 240.0, 300.0])
        assert uppers[-1] is None

    def test_zone_bounds_are_contiguous(self) -> None:
        bounds = _scale_to_watts(200, _ZONE_FRACTIONS[PowerZoneModel.COGGAN_7])

        for earlier, later in pairwise(bounds):
            assert earlier.upper == later.lower


class TestScaleToWatts:
    def test_rejects_non_positive_ftp(self) -> None:
        with pytest.raises(deal.PreContractError):
            _scale_to_watts(0, _ZONE_FRACTIONS[PowerZoneModel.COGGAN_7])

    def test_rejects_fewer_than_two_zones(self) -> None:
        with pytest.raises(deal.PreContractError):
            _scale_to_watts(200, (("Only zone", None),))

    def test_rejects_a_table_that_is_not_open_ended(self) -> None:
        with pytest.raises(deal.PreContractError):
            _scale_to_watts(200, (("Zone 1", 0.5), ("Zone 2", 1.0)))


class TestAccumulateZoneDurations:
    def test_assigns_each_interval_to_its_earlier_samples_zone(self) -> None:
        samples = [
            (START, 100.0),
            (START + timedelta(seconds=1), 200.0),
            (START + timedelta(seconds=2), 200.0),
        ]

        durations = _accumulate_zone_durations(samples, [110.0, 150.0])

        assert durations == [timedelta(seconds=1), timedelta(0), timedelta(seconds=1)]

    def test_boundary_value_falls_into_the_lower_zone(self) -> None:
        """Upper bounds are inclusive, so exactly 110W stays in zone 1."""
        samples = [(START, 110.0), (START + timedelta(seconds=1), 999.0)]

        durations = _accumulate_zone_durations(samples, [110.0, 150.0])

        assert durations == [timedelta(seconds=1), timedelta(0), timedelta(0)]

    def test_excludes_a_paused_gap(self) -> None:
        samples = [(START, 100.0), (START + timedelta(seconds=64), 100.0)]

        durations = _accumulate_zone_durations(samples, [110.0, 150.0])

        assert durations == [timedelta(0), timedelta(0), timedelta(0)]

    def test_rejects_empty_upper_edges(self) -> None:
        with pytest.raises(deal.PreContractError):
            _accumulate_zone_durations([(START, 100.0)], [])

    def test_rejects_upper_edges_not_strictly_ascending(self) -> None:
        with pytest.raises(deal.PreContractError):
            _accumulate_zone_durations([(START, 100.0)], [150.0, 150.0])


class TestPowerZoneDistribution:
    def test_default_model_is_coggan_seven(self) -> None:
        result = power_zone_distribution(_records_with_power(130, 130), ftp=200)

        assert result is not None
        assert result.zone_model == DEFAULT_POWER_ZONE_MODEL
        assert len(result.zones) == 7

    @pytest.mark.parametrize(
        ("model", "expected_zone_count"),
        [
            (PowerZoneModel.POLARIZED_3, 3),
            (PowerZoneModel.CLASSIC_5, 5),
            (PowerZoneModel.BRITISH_CYCLING_6, 6),
            (PowerZoneModel.COGGAN_7, 7),
        ],
    )
    def test_selected_model_determines_zone_count(
        self, model: PowerZoneModel, expected_zone_count: int
    ) -> None:
        result = power_zone_distribution(
            _records_with_power(130, 130), ftp=200, zone_model=model
        )

        assert result is not None
        assert result.zone_model == model
        assert len(result.zones) == expected_zone_count

    def test_steady_power_falls_entirely_into_one_zone(self) -> None:
        # 130W at FTP=200 is 65% -> between the 55% and 75% bounds: zone 2.
        records = _records_with_power(*([130] * 10))

        result = power_zone_distribution(records, ftp=200)

        assert result is not None
        assert result.zone(2).duration == timedelta(seconds=9)
        assert result.zone(1).duration == timedelta(0)

    def test_coasting_falls_into_the_lowest_zone(self) -> None:
        records = _records_with_power(0, 0)

        result = power_zone_distribution(records, ftp=200)

        assert result is not None
        assert result.zone(1).duration == timedelta(seconds=1)

    def test_very_high_power_falls_into_the_open_ended_top_zone(self) -> None:
        records = _records_with_power(1000, 1000)

        result = power_zone_distribution(records, ftp=200)

        assert result is not None
        assert result.zone(7).duration == timedelta(seconds=1)

    def test_excludes_a_paused_gap_from_every_zone(self) -> None:
        records = _records_with_power(130, 130, gap_s=64)

        result = power_zone_distribution(records, ftp=200)

        assert result is not None
        assert result.total_duration == timedelta(0)

    def test_ignores_records_without_a_power_reading(self) -> None:
        records = [
            RecordPoint(timestamp=START, heart_rate=140),
            *_records_with_power(130, 130),
        ]

        result = power_zone_distribution(records, ftp=200)

        assert result is not None
        assert result.total_duration == timedelta(seconds=1)

    def test_none_without_ftp(self) -> None:
        records = _records_with_power(130, 130)

        assert power_zone_distribution(records, ftp=None) is None

    def test_none_without_any_power_data(self) -> None:
        records = [RecordPoint(timestamp=START, heart_rate=140)]

        assert power_zone_distribution(records, ftp=200) is None

    def test_none_for_a_single_power_sample(self) -> None:
        records = _records_with_power(130)

        assert power_zone_distribution(records, ftp=200) is None

    def test_rejects_non_positive_ftp(self) -> None:
        records = _records_with_power(130, 130)

        with pytest.raises(deal.PreContractError):
            power_zone_distribution(records, ftp=0)

    def test_zone_indices_are_one_based_and_contiguous(self) -> None:
        result = power_zone_distribution(_records_with_power(130, 130), ftp=200)

        assert result is not None
        assert [zone.index for zone in result.zones] == list(range(1, 8))

    def test_total_duration_sums_all_zones(self) -> None:
        records = _records_with_power(*([130] * 5))

        result = power_zone_distribution(records, ftp=200)

        assert result is not None
        expected = sum((zone.duration for zone in result.zones), timedelta(0))
        assert result.total_duration == expected

    def test_zone_rejects_an_out_of_range_index(self) -> None:
        result = power_zone_distribution(_records_with_power(130, 130), ftp=200)

        assert result is not None
        with pytest.raises(deal.PreContractError):
            result.zone(99)
