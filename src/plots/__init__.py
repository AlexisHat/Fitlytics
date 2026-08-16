"""Chart construction for workout and recovery data."""

from plots.gps_map import (
    METRICS,
    MetricKey,
    MetricScale,
    MetricSpec,
    available_metrics,
    build_gps_map_figure,
)
from plots.interval_chart import plot_power_with_intervals
from plots.interval_detail import plot_interval_detail
from plots.series import available_channels, build_time_series
from plots.timeline import XAxisMode, build_timeline_figure
from plots.zones import POWER_ZONE_MODEL_LABELS, plot_heart_rate_zones, plot_power_zones

__all__ = [
    "METRICS",
    "POWER_ZONE_MODEL_LABELS",
    "MetricKey",
    "MetricScale",
    "MetricSpec",
    "XAxisMode",
    "available_channels",
    "available_metrics",
    "build_gps_map_figure",
    "build_time_series",
    "build_timeline_figure",
    "plot_heart_rate_zones",
    "plot_interval_detail",
    "plot_power_with_intervals",
    "plot_power_zones",
]
