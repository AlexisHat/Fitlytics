"""Open a workout's timeline chart in the browser for manual inspection."""

import sys
from pathlib import Path

from plots.series import build_time_series
from plots.timeline import build_timeline_figure
from readers.fit import import_fit_file
from validation.workout import validate_workout

DEFAULT_SOURCE = Path("data/private/07-162x8minFTP.fit")


def main() -> None:
    """Build the timeline figure for a FIT file and open it in the browser."""
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    workout, _ = validate_workout(import_fit_file(source))
    series = build_time_series(workout.records)
    build_timeline_figure(series).show()


if __name__ == "__main__":
    main()
