"""Pydantic model for a single day of recovery metrics from a Whoop export."""

from datetime import date, datetime

from pydantic import BaseModel


class RecoveryDay(BaseModel):
    """Recovery metrics for a single day, imported from a Whoop export.

    Attributes:
        date: Local calendar date the cycle belongs to.
        cycle_start: Start of the physiological cycle, UTC.
        recovery_score: Whoop recovery score in percent, if available.
        resting_hr: Resting heart rate in beats per minute, if available.
        hrv_ms: Heart rate variability in milliseconds, if available.
        skin_temp_c: Skin temperature in degrees Celsius, if available.
        respiratory_rate: Breaths per minute, if available.
        blood_oxygen: Blood oxygen saturation in percent, if available.
    """

    date: date
    cycle_start: datetime
    recovery_score: int | None = None
    resting_hr: int | None = None
    hrv_ms: float | None = None
    skin_temp_c: float | None = None
    respiratory_rate: float | None = None
    blood_oxygen: float | None = None
