"""Build a workout's GPS-track map and write it to HTML for manual inspection."""

import sys
from pathlib import Path

from plots.gps_map import MetricKey, build_gps_map_figure
from plots.series import build_time_series
from readers.fit import import_fit_file
from validation.workout import validate_workout

DEFAULT_SOURCE = Path("data/private/07-162x8minFTP.fit")
DEFAULT_METRIC = MetricKey.POWER
OUTPUT = Path("scripts/gps_map_preview.html")


def main() -> None:
    """Build the GPS map figure for a FIT file and write it to an HTML file."""
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    metric = MetricKey(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_METRIC
    workout, _ = validate_workout(import_fit_file(source))
    series = build_time_series(workout.records)
    fig = build_gps_map_figure(series, metric)
    fig.write_html(OUTPUT)
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
