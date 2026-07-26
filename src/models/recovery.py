"""Pydantic model for a single day of recovery metrics from a Whoop export."""

from datetime import date

from pydantic import BaseModel, NonNegativeFloat, PositiveInt

from models.types import PercentFloat, PercentInt, UtcDatetime


class RecoveryDay(BaseModel):
    """Recovery metrics for a single day, imported from a Whoop export.

    Attributes:
        date: Local calendar day the cycle reports on. A Whoop cycle spans
            one sleep and the waking day that follows it, so this is not
            simply the day the cycle started on; see
            :func:`readers.whoop._build_recovery_day`.
        cycle_start: Start of the physiological cycle, UTC.
        recovery_score: Whoop recovery score in percent, if available.
        resting_hr: Resting heart rate in beats per minute, if available.
        hrv_ms: Heart rate variability in milliseconds, if available.
        skin_temp_c: Skin temperature in degrees Celsius, if available.
        respiratory_rate: Breaths per minute, if available.
        blood_oxygen: Blood oxygen saturation in percent, if available.
    """

    date: date
    cycle_start: UtcDatetime
    recovery_score: PercentInt | None = None
    resting_hr: PositiveInt | None = None
    hrv_ms: NonNegativeFloat | None = None
    skin_temp_c: float | None = None
    respiratory_rate: NonNegativeFloat | None = None
    blood_oxygen: PercentFloat | None = None
