"""Pydantic models for a single training session imported from a FIT file."""

from enum import StrEnum
from typing import Self

from pydantic import (
    BaseModel,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    model_validator,
)

from models.types import Latitude, Longitude, PositiveTimedelta, UtcDatetime


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
        latitude: Decimal-degree latitude (WGS84), if a GPS fix was
            available.
        longitude: Decimal-degree longitude (WGS84), if a GPS fix was
            available.
    """

    timestamp: UtcDatetime
    heart_rate: NonNegativeInt | None = None
    power: NonNegativeInt | None = None
    cadence: NonNegativeInt | None = None
    distance_m: NonNegativeFloat | None = None
    speed_ms: NonNegativeFloat | None = None
    altitude_m: float | None = None
    grade_pct: float | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None


class WorkoutCategory(StrEnum):
    """Athlete-assigned training category, chosen at upload time.

    Purely a self-classification of intent — nothing here is derived from
    the recorded data itself, unlike e.g. :mod:`intervals`' detection.

    Attributes:
        GRUNDLAGE: Steady, low-intensity endurance ride.
        INTERVALLE: A planned interval session; see
            :class:`PlannedIntervalSpec` for the session's structure.
        GROUPRIDE: Social or race-pace group ride, intensity not
            self-directed.
        RECOVERY: Deliberately easy ride for recovery.
        SONSTIGE: Anything not covered by the other categories.
    """

    GRUNDLAGE = "grundlage"
    INTERVALLE = "intervalle"
    GROUPRIDE = "groupride"
    RECOVERY = "recovery"
    SONSTIGE = "sonstige"


class PlannedIntervalSpec(BaseModel):
    """The athlete's planned interval structure, entered at upload time.

    A statement of intent from the training plan, independent of what
    :mod:`intervals` later detects from the recorded power data — the two
    are never reconciled automatically.

    Attributes:
        repetitions: How many repeats the plan called for.
        duration: Planned duration of a single repeat.
        target_power_w: Planned power target for a single repeat, in watts.
    """

    repetitions: PositiveInt
    duration: PositiveTimedelta
    target_power_w: PositiveInt


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
        name: The athlete's own title for the session, if given at upload
            time; None falls back to :attr:`display_name`, not to a
            fabricated title.
        category: The athlete-assigned training category, if chosen at
            upload time.
        planned_intervals: The plan's interval structure, if ``category`` is
            :attr:`WorkoutCategory.INTERVALLE` and it was filled in at
            upload time; None otherwise.
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
    name: str | None = None
    category: WorkoutCategory | None = None
    planned_intervals: PlannedIntervalSpec | None = None
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

    @model_validator(mode="after")
    def _check_planned_intervals_need_interval_category(self) -> Self:
        """Reject a planned interval spec without the matching category.

        A plan only makes sense for a session actually categorized as
        intervals — this catches an inconsistent construction (e.g. a stale
        category edit) rather than silently keeping an orphaned plan.

        Raises:
            ValueError: If planned_intervals is set but category is not
                WorkoutCategory.INTERVALLE.
        """
        if (
            self.planned_intervals is not None
            and self.category is not WorkoutCategory.INTERVALLE
        ):
            raise ValueError(
                "planned_intervals requires category to be WorkoutCategory.INTERVALLE"
            )
        return self

    @property
    def has_gps_track(self) -> bool:
        """Whether the workout has enough GPS fixes to draw a track on a map.

        Returns:
            True if at least two records carry both latitude and
            longitude, the minimum needed to draw a line; False otherwise,
            e.g. for an indoor trainer session with no GPS at all.

        >>> from datetime import UTC, datetime
        >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
        >>> indoor = Workout(
        ...     start_time=start,
        ...     sport="cycling",
        ...     records=[RecordPoint(timestamp=start, power=200)],
        ... )
        >>> indoor.has_gps_track
        False
        """
        gps_fixes = sum(
            1
            for record in self.records
            if record.latitude is not None and record.longitude is not None
        )
        return gps_fixes >= 2

    @property
    def display_name(self) -> str:
        """The workout's title: ``name`` if given, else "Training am <date>".

        Returns:
            ``name``, or a generated title from the UTC start date if none
            was given at upload time.

        >>> from datetime import UTC, datetime
        >>> start = datetime(2026, 7, 16, 14, 0, 0, tzinfo=UTC)
        >>> records = [RecordPoint(timestamp=start, power=200)]
        >>> Workout(start_time=start, sport="cycling", records=records).display_name
        'Training am 2026-07-16'
        >>> named = Workout(
        ...     start_time=start,
        ...     sport="cycling",
        ...     name="Feierabendrunde",
        ...     records=records,
        ... )
        >>> named.display_name
        'Feierabendrunde'
        """
        return self.name or f"Training am {self.start_time.date().isoformat()}"
