"""Which Functional Threshold Power a given workout should be measured against."""

from models import Workout


def effective_ftp(workout: Workout, profile_ftp: int | None) -> int | None:
    """The FTP a workout's analysis should be scaled to.

    The workout's own value wins, because it belongs to the day the ride
    was recorded: an interval type derived from today's profile FTP would
    silently rewrite itself every time the athlete retests. The profile
    value only fills in for a workout that carries none, e.g. a FIT file
    recorded on a head unit with no FTP configured.

    Args:
        workout: The workout being analysed.
        profile_ftp: The athlete's current FTP from the sidebar, or None.

    Returns:
        The FTP to scale this workout to, or None if neither is known.

    >>> from datetime import UTC, datetime
    >>> from models import RecordPoint
    >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
    >>> records = [RecordPoint(timestamp=start, power=200)]
    >>> ride = Workout(start_time=start, sport="cycling", records=records)
    >>> effective_ftp(ride.model_copy(update={"ftp_watts": 210}), 223)
    210
    >>> effective_ftp(ride, 223)
    223
    >>> effective_ftp(ride, None)
    """
    return workout.ftp_watts if workout.ftp_watts is not None else profile_ftp
