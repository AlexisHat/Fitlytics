"""Static bar charts of a workout's heart-rate and power zone distributions."""

from typing import Final

from matplotlib.figure import Figure

from analysis.constants import PowerZoneModel
from analysis.heart_rate_zones import HeartRateZoneDistribution
from analysis.power_zones import PowerZoneDistribution

_HR_ZONE_COLOR: Final = "#2ca02c"
"""Same green as the heart-rate panel in the interactive timeline."""

_POWER_ZONE_COLOR: Final = "#c1440e"
"""Same orange as the power panel in the interactive timeline."""

_HR_ZONE_LABELS: Final[tuple[str, ...]] = tuple(f"Zone {i}" for i in range(1, 6))

POWER_ZONE_MODEL_LABELS: Final[dict[PowerZoneModel, str]] = {
    PowerZoneModel.POLARIZED_3: "3 Zonen (polarisiert)",
    PowerZoneModel.CLASSIC_5: "5 Zonen (klassisch)",
    PowerZoneModel.BRITISH_CYCLING_6: "6 Zonen (British Cycling)",
    PowerZoneModel.COGGAN_7: "7 Zonen (Coggan/Allen)",
}


def plot_heart_rate_zones(distribution: HeartRateZoneDistribution) -> Figure:
    """Draw a bar chart of time spent in each Karvonen heart-rate zone.

    Args:
        distribution: A workout's heart-rate zone distribution, e.g. from
            :func:`analysis.heart_rate_zones.heart_rate_zone_distribution`.

    Returns:
        A matplotlib figure with one bar per zone (1 to 5), zone duration
        in minutes on the y-axis.

    >>> from datetime import timedelta
    >>> distribution = HeartRateZoneDistribution(
    ...     zone_1=timedelta(minutes=1),
    ...     zone_2=timedelta(minutes=2),
    ...     zone_3=timedelta(minutes=3),
    ...     zone_4=timedelta(minutes=4),
    ...     zone_5=timedelta(minutes=5),
    ... )
    >>> fig = plot_heart_rate_zones(distribution)
    >>> [round(float(bar.get_height()), 1) for bar in fig.axes[0].patches]
    [1.0, 2.0, 3.0, 4.0, 5.0]
    """
    minutes = [
        zone.total_seconds() / 60
        for zone in (
            distribution.zone_1,
            distribution.zone_2,
            distribution.zone_3,
            distribution.zone_4,
            distribution.zone_5,
        )
    ]
    fig = Figure()
    ax = fig.add_subplot()
    ax.bar(_HR_ZONE_LABELS, minutes, color=_HR_ZONE_COLOR)
    ax.set_ylabel("Minuten")
    ax.set_title("Herzfrequenzzonen (Karvonen)")
    fig.tight_layout()
    return fig


def plot_power_zones(distribution: PowerZoneDistribution) -> Figure:
    """Draw a bar chart of time spent in each power zone.

    Args:
        distribution: A workout's power zone distribution, e.g. from
            :func:`analysis.power_zones.power_zone_distribution`.

    Returns:
        A matplotlib figure with one bar per zone of the distribution's
        model, zone duration in minutes on the y-axis, and the model and
        FTP named in the title.

    >>> from datetime import timedelta
    >>> from analysis.power_zones import PowerZone
    >>> distribution = PowerZoneDistribution(
    ...     zone_model=PowerZoneModel.POLARIZED_3,
    ...     ftp=200,
    ...     zones=(
    ...         PowerZone(
    ...             index=1,
    ...             name="Low intensity",
    ...             lower_bound=0,
    ...             upper_bound=160,
    ...             duration=timedelta(minutes=10),
    ...         ),
    ...         PowerZone(
    ...             index=2,
    ...             name="Threshold",
    ...             lower_bound=160,
    ...             upper_bound=200,
    ...             duration=timedelta(minutes=5),
    ...         ),
    ...         PowerZone(
    ...             index=3,
    ...             name="High intensity",
    ...             lower_bound=200,
    ...             upper_bound=None,
    ...             duration=timedelta(minutes=2),
    ...         ),
    ...     ),
    ... )
    >>> fig = plot_power_zones(distribution)
    >>> [round(float(bar.get_height()), 1) for bar in fig.axes[0].patches]
    [10.0, 5.0, 2.0]
    """
    labels = [zone.name for zone in distribution.zones]
    minutes = [zone.duration.total_seconds() / 60 for zone in distribution.zones]
    fig = Figure()
    ax = fig.add_subplot()
    ax.bar(labels, minutes, color=_POWER_ZONE_COLOR)
    ax.set_ylabel("Minuten")
    model_label = POWER_ZONE_MODEL_LABELS[distribution.zone_model]
    ax.set_title(f"Leistungszonen ({model_label}, FTP {distribution.ftp} W)")
    ax.tick_params(axis="x", rotation=30)
    for label in ax.get_xticklabels():
        label.set_horizontalalignment("right")
    fig.tight_layout()
    return fig
