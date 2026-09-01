"""Tests for the shared training-load intensity colour scale."""

from plots.intensity import INTENSITY_STOPS, intensity_color, intensity_rgb


def test_intensity_color_is_green_at_zero_percent() -> None:
    assert intensity_color(0) == "#bbf7d0"


def test_intensity_color_is_red_at_hundred_percent() -> None:
    assert intensity_color(100) == "#dc2626"


def test_intensity_rgb_matches_every_defined_stop_exactly() -> None:
    for pct, rgb in INTENSITY_STOPS:
        assert intensity_rgb(pct) == rgb


def test_intensity_rgb_interpolates_between_two_stops() -> None:
    (low_pct, low_rgb), (high_pct, high_rgb) = INTENSITY_STOPS[1], INTENSITY_STOPS[2]
    midpoint = intensity_rgb((low_pct + high_pct) // 2)

    for channel, low, high in zip(midpoint, low_rgb, high_rgb, strict=True):
        assert min(low, high) <= channel <= max(low, high)
    assert midpoint not in (low_rgb, high_rgb)
