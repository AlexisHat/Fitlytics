"""Tests for plots.zones."""

from datetime import timedelta
from typing import cast

from matplotlib.container import BarContainer
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from analysis.constants import PowerZoneModel
from analysis.heart_rate_zones import HeartRateZoneDistribution
from analysis.power_zones import PowerZone, PowerZoneDistribution
from plots.zones import plot_heart_rate_zones, plot_power_zones


def _bars(fig: Figure) -> list[Rectangle]:
    return cast(BarContainer, fig.axes[0].containers[0]).patches


_HR_DISTRIBUTION = HeartRateZoneDistribution(
    zone_1=timedelta(minutes=1),
    zone_2=timedelta(minutes=2),
    zone_3=timedelta(minutes=3),
    zone_4=timedelta(minutes=4),
    zone_5=timedelta(minutes=5),
)

_POWER_DISTRIBUTION = PowerZoneDistribution(
    zone_model=PowerZoneModel.POLARIZED_3,
    ftp=200,
    zones=(
        PowerZone(
            index=1,
            name="Low intensity",
            lower_bound=0,
            upper_bound=160,
            duration=timedelta(minutes=10),
        ),
        PowerZone(
            index=2,
            name="Threshold",
            lower_bound=160,
            upper_bound=200,
            duration=timedelta(minutes=5),
        ),
        PowerZone(
            index=3,
            name="High intensity",
            lower_bound=200,
            upper_bound=None,
            duration=timedelta(minutes=2),
        ),
    ),
)


def test_plot_heart_rate_zones_draws_one_bar_per_zone() -> None:
    fig = plot_heart_rate_zones(_HR_DISTRIBUTION)

    assert len(_bars(fig)) == 5


def test_plot_heart_rate_zones_converts_durations_to_minutes() -> None:
    fig = plot_heart_rate_zones(_HR_DISTRIBUTION)

    heights = [float(bar.get_height()) for bar in _bars(fig)]
    assert heights == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_plot_heart_rate_zones_labels_the_zones_one_to_five() -> None:
    fig = plot_heart_rate_zones(_HR_DISTRIBUTION)

    labels = [tick.get_text() for tick in fig.axes[0].get_xticklabels()]
    assert labels == ["Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5"]


def test_plot_power_zones_draws_one_bar_per_zone_of_the_model() -> None:
    fig = plot_power_zones(_POWER_DISTRIBUTION)

    assert len(_bars(fig)) == 3


def test_plot_power_zones_converts_durations_to_minutes() -> None:
    fig = plot_power_zones(_POWER_DISTRIBUTION)

    heights = [float(bar.get_height()) for bar in _bars(fig)]
    assert heights == [10.0, 5.0, 2.0]


def test_plot_power_zones_labels_bars_with_zone_names() -> None:
    fig = plot_power_zones(_POWER_DISTRIBUTION)

    labels = [tick.get_text() for tick in fig.axes[0].get_xticklabels()]
    assert labels == ["Low intensity", "Threshold", "High intensity"]


def test_plot_power_zones_names_the_model_and_ftp_in_the_title() -> None:
    fig = plot_power_zones(_POWER_DISTRIBUTION)

    title = fig.axes[0].get_title()
    assert "polarisiert" in title
    assert "FTP 200 W" in title
