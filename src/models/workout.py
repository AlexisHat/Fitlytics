"""Pydantic models for a single training session imported from a FIT file."""

from datetime import datetime

from pydantic import BaseModel, Field


class RecordPoint(BaseModel):
    """A single timestamped measurement within a workout.

    Attributes:
        timestamp: Time of the measurement, UTC.
        heart_rate: Heart rate in beats per minute, if recorded.
        power: Power output in watts, if a power meter is present.
        cadence: Pedalling cadence in revolutions per minute, if recorded.
        distance_m: Cumulative distance in metres, if recorded.
        speed_ms: Instantaneous speed in metres per second, if recorded.
        altitude_m: Altitude in metres, if recorded.
    """

    timestamp: datetime
    heart_rate: int | None = None
    power: int | None = None
    cadence: int | None = None
    distance_m: float | None = None
    speed_ms: float | None = None
    altitude_m: float | None = None


class Workout(BaseModel):
    """A single training session imported from a FIT file.

    Attributes:
        start_time: Start of the session, UTC.
        sport: Sport as reported by the device (e.g. "cycling").
        sub_sport: More specific sport classification, if available.
        ftp_watts: Functional Threshold Power configured on the device at
            recording time, if available.
        records: Time-ordered measurements of the session; at least one.
    """

    start_time: datetime
    sport: str
    sub_sport: str | None = None
    ftp_watts: int | None = None
    records: list[RecordPoint] = Field(min_length=1)
