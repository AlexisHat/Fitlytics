"""Annotated field types shared by the Fitlytics data models.

These carry the constraints that follow from the quantity itself, so that no
model can be constructed in a state later code would have to guard against.
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, Field


def _require_utc(value: datetime) -> datetime:
    """Reject a naive datetime and normalise an aware one to UTC.

    A naive value is rejected rather than assumed to be UTC. Guessing the
    zone would shift every timestamp of a differently configured device by
    hours, and nothing downstream could still notice the shift.

    Args:
        value: The datetime to normalise.

    Returns:
        The same instant expressed in UTC.

    Raises:
        ValueError: If ``value`` carries no timezone information.

    >>> from datetime import timedelta, timezone
    >>> berlin = timezone(timedelta(hours=2))
    >>> _require_utc(datetime(2026, 7, 23, 1, 43, 25, tzinfo=berlin))
    datetime.datetime(2026, 7, 22, 23, 43, 25, tzinfo=datetime.timezone.utc)
    >>> _require_utc(datetime(2026, 7, 23, 1, 43, 25))
    Traceback (most recent call last):
        ...
    ValueError: datetime is naive; a timezone-aware value is required
    """
    if value.utcoffset() is None:
        raise ValueError("datetime is naive; a timezone-aware value is required")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_require_utc)]
"""A timezone-aware datetime, normalised to UTC when the model is built."""

PercentInt = Annotated[int, Field(ge=0, le=100)]
"""A whole percentage; values outside 0-100 are impossible by definition."""

PercentFloat = Annotated[float, Field(ge=0, le=100)]
"""A fractional percentage; values outside 0-100 are impossible by definition."""

Latitude = Annotated[float, Field(ge=-90, le=90)]
"""Decimal-degree latitude; values outside -90 to 90 are impossible by
definition, regardless of how implausible the position is otherwise."""

Longitude = Annotated[float, Field(ge=-180, le=180)]
"""Decimal-degree longitude; values outside -180 to 180 are impossible by
definition, regardless of how implausible the position is otherwise."""
