"""Tests for analysis.efficiency."""

from datetime import UTC, datetime, timedelta

from analysis.efficiency import decoupling_pct, efficiency_factor
from models import RecordPoint

START = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)


def _record(
    offset_s: int, power: int | None = None, heart_rate: int | None = None
) -> RecordPoint:
    return RecordPoint(
        timestamp=START + timedelta(seconds=offset_s),
        power=power,
        heart_rate=heart_rate,
    )


class TestEfficiencyFactor:
    def test_prefers_normalized_power_over_avg_power(self) -> None:
        assert efficiency_factor(200.0, 100.0, 150.0) == 200.0 / 150.0

    def test_falls_back_to_avg_power_without_normalized_power(self) -> None:
        assert efficiency_factor(None, 150.0, 150.0) == 1.0

    def test_none_without_any_power_figure(self) -> None:
        assert efficiency_factor(None, None, 150.0) is None

    def test_none_without_heart_rate(self) -> None:
        assert efficiency_factor(200.0, 150.0, None) is None

    def test_none_when_heart_rate_is_zero(self) -> None:
        assert efficiency_factor(200.0, 150.0, 0.0) is None


class TestDecouplingPct:
    def test_zero_for_a_perfectly_steady_ratio(self) -> None:
        records = [_record(i, power=200, heart_rate=150) for i in range(20)]

        assert decoupling_pct(records) == 0.0

    def test_positive_when_the_ratio_drops_in_the_second_half(self) -> None:
        """Same power, higher heart rate later = aerobic fatigue."""
        records = [_record(i, power=200, heart_rate=140) for i in range(30)] + [
            _record(i, power=200, heart_rate=160) for i in range(30, 60)
        ]

        result = decoupling_pct(records)

        assert result is not None
        assert result > 0

    def test_negative_when_the_ratio_rises_in_the_second_half(self) -> None:
        records = [_record(i, power=200, heart_rate=160) for i in range(30)] + [
            _record(i, power=200, heart_rate=140) for i in range(30, 60)
        ]

        result = decoupling_pct(records)

        assert result is not None
        assert result < 0

    def test_none_for_a_very_short_workout(self) -> None:
        assert decoupling_pct([_record(0, power=200, heart_rate=150)]) is None

    def test_none_without_any_power_data(self) -> None:
        records = [_record(i, heart_rate=150) for i in range(20)]

        assert decoupling_pct(records) is None

    def test_none_without_any_heart_rate_data(self) -> None:
        records = [_record(i, power=200) for i in range(20)]

        assert decoupling_pct(records) is None

    def test_none_when_only_the_second_half_has_power_data(self) -> None:
        records = [_record(i, heart_rate=150) for i in range(10)] + [
            _record(i, power=200, heart_rate=150) for i in range(10, 20)
        ]

        assert decoupling_pct(records) is None
