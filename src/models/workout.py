"""Pydantic models for a single training session imported from a FIT file."""

from pydantic import BaseModel, Field, NonNegativeFloat, NonNegativeInt, PositiveInt

from models.types import UtcDatetime


class RecordPoint(BaseModel):
    """A single timestamped measurement within a workout.

    Zero is a genuine reading for power, cadence and speed — a rider coasting
    downhill produces long stretches of it — so only negative values are
    rejected here. Implausibly *high* readings are a sensor artefact rather
    than an impossibility and are handled by :mod:`validation` instead.

    Attributes:
        timestamp: Time of the measurement, UTC.
        heart_rate: Heart rate in beats per minute, if recorded.
        power: Power output in watts, if a power meter is present.
        cadence: Pedalling cadence in revolutions per minute, if recorded.
        distance_m: Cumulative distance in metres, if recorded.
        speed_ms: Instantaneous speed in metres per second, if recorded.
        altitude_m: Altitude in metres, if recorded; may be negative.
        grade_pct: Instantaneous gradient in percent, if recorded; may be
            negative on a descent.
    """

    timestamp: UtcDatetime
    heart_rate: NonNegativeInt | None = None
    power: NonNegativeInt | None = None
    cadence: NonNegativeInt | None = None
    distance_m: NonNegativeFloat | None = None
    speed_ms: NonNegativeFloat | None = None
    altitude_m: float | None = None
    grade_pct: float | None = None


class Workout(BaseModel):
    """A single training session imported from a FIT file.

    The ``device_*`` and ``total_*`` attributes are figures the recording
    device already computed from its own (often proprietary, e.g. barometric
    smoothing for elevation) algorithms. They are kept as reported rather
    than recomputed from records — see ``docs/entscheidungen.md`` for which
    metrics are trusted from the device and which are computed by Fitlytics
    itself.

    Attributes:
        start_time: Start of the session, UTC.
        sport: Sport as reported by the device (e.g. "cycling").
        sub_sport: More specific sport classification, if available.
        ftp_watts: Functional Threshold Power configured on the device at
            recording time, if available.
        total_ascent_m: Total climbed elevation, if available.
        total_descent_m: Total descended elevation, if available.
        avg_grade_pct: Average gradient over the session, if available.
        total_work_j: Total mechanical work in joules, if available.
        device_normalized_power: Normalized Power as computed by the
            device, if available.
        device_intensity_factor: Intensity Factor as computed by the
            device, if available.
        device_training_stress_score: Training Stress Score as computed by
            the device, if available.
        records: Time-ordered measurements of the session; at least one.
    """

    start_time: UtcDatetime
    sport: str = Field(min_length=1)
    sub_sport: str | None = None
    ftp_watts: PositiveInt | None = None
    total_ascent_m: NonNegativeFloat | None = None
    total_descent_m: NonNegativeFloat | None = None
    avg_grade_pct: float | None = None
    total_work_j: NonNegativeFloat | None = None
    device_normalized_power: NonNegativeInt | None = None
    device_intensity_factor: NonNegativeFloat | None = None
    device_training_stress_score: NonNegativeFloat | None = None
    records: list[RecordPoint] = Field(min_length=1)
