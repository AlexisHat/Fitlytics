"""Power-zone distribution for a single training ride.

This module is the power-based counterpart to the heart-rate zone analysis.
It converts a list of :class:`RecordPoint` samples into the time spent in
each power zone, relative to the rider's FTP.

Heart-rate zones have one commonly used definition (Karvonen, five zones),
power zones do not: three-, five-, six- and seven-zone models are all in
active use.  The caller therefore selects a model via
:class:`PowerZoneModel`; the classic seven-zone Coggan model is the default.

Because the number of zones varies per model, the result exposes its zones as
a sequence of :class:`PowerZone` objects instead of fixed ``zone_1 .. zone_n``
fields.  Zone numbering is 1-based, matching how the models are published.

Only moving time is counted: gaps longer than ``PAUSE_GAP_THRESHOLD`` are
attributed to no zone, the same as elsewhere in the analysis.
"""

from bisect import bisect_left
from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from itertools import pairwise

import deal
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, PositiveInt

from analysis.workout import PAUSE_GAP_THRESHOLD
from models import RecordPoint


class PowerZoneModel(StrEnum):
    """Selectable definitions of FTP-based cycling power zones.

    Attributes:
        POLARIZED_3: Three zones around the two ventilatory thresholds, as
            used in polarized-training literature (Seiler).
        CLASSIC_5: Five zones, the Coggan model with its three high-intensity
            zones collapsed into one.
        BRITISH_CYCLING_6: Six zones, the Coggan model without the separate
            neuromuscular sprint zone.
        COGGAN_7: Seven zones (Coggan/Allen). Default model.
    """

    POLARIZED_3 = "polarized_3"
    CLASSIC_5 = "classic_5"
    BRITISH_CYCLING_6 = "british_cycling_6"
    COGGAN_7 = "coggan_7"


DEFAULT_POWER_ZONE_MODEL = PowerZoneModel.COGGAN_7


class PowerZone(BaseModel):
    """A single power zone and the time spent in it.

    Attributes:
        index: 1-based zone number within its model.
        name: Human-readable zone name, e.g. ``"Tempo"``.
        lower_bound: Lower power bound in watts, exclusive.
        upper_bound: Upper power bound in watts, inclusive. ``None`` for the
            open-ended top zone.
        duration: Moving time spent in this zone.
    """

    index: PositiveInt
    name: str
    lower_bound: NonNegativeFloat
    upper_bound: float | None = None
    duration: timedelta


class PowerZoneDistribution(BaseModel):
    """Time spent in each power zone of the selected model.

    Covers moving time only: paused stretches contribute to no zone, the
    same as elsewhere in the analysis. Coasting (zero watts) counts towards
    the lowest zone.

    Attributes:
        zone_model: The model the zones were derived from.
        ftp: Functional threshold power in watts the zones were scaled to.
        zones: The zones in ascending order, starting at index 1.
    """

    zone_model: PowerZoneModel
    ftp: PositiveInt
    zones: tuple[PowerZone, ...]

    @property
    def total_duration(self) -> timedelta:
        """Total moving time covered by all zones.

        Returns:
            The sum of all zone durations.
        """
        return sum((zone.duration for zone in self.zones), timedelta(0))

    @deal.pre(lambda _: 1 <= _.index <= len(_.self.zones))
    def zone(self, index: int) -> PowerZone:
        """Return a zone by its 1-based number.

        Args:
            index: Zone number between 1 and the model's zone count.

        Returns:
            The requested zone.
        """
        return self.zones[index - 1]


class _ZoneBounds(BaseModel):
    """Internal watt bounds of one zone before durations are known.

    Attributes:
        name: Human-readable zone name.
        lower: Lower power bound in watts, exclusive.
        upper: Upper power bound in watts, inclusive, or ``None`` if open.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    lower: NonNegativeFloat
    upper: float | None = None


# Zone tables per model, as (name, upper bound as a fraction of FTP). The
# last entry of each table is open-ended and therefore carries ``None``.
# Percentages follow the published Coggan/Allen power-training-zone scheme;
# the shorter models are that same scheme with its top zones collapsed.
_ZONE_FRACTIONS: dict[PowerZoneModel, tuple[tuple[str, float | None], ...]] = {
    PowerZoneModel.POLARIZED_3: (
        ("Low intensity", 0.80),
        ("Threshold", 1.00),
        ("High intensity", None),
    ),
    PowerZoneModel.CLASSIC_5: (
        ("Active recovery", 0.55),
        ("Endurance", 0.75),
        ("Tempo", 0.90),
        ("Lactate threshold", 1.05),
        ("VO2max and above", None),
    ),
    PowerZoneModel.BRITISH_CYCLING_6: (
        ("Active recovery", 0.55),
        ("Endurance", 0.75),
        ("Tempo", 0.90),
        ("Lactate threshold", 1.05),
        ("VO2max", 1.20),
        ("Anaerobic capacity", None),
    ),
    PowerZoneModel.COGGAN_7: (
        ("Active recovery", 0.55),
        ("Endurance", 0.75),
        ("Tempo", 0.90),
        ("Lactate threshold", 1.05),
        ("VO2max", 1.20),
        ("Anaerobic capacity", 1.50),
        ("Neuromuscular power", None),
    ),
}


@deal.pre(lambda _: _.ftp > 0)
@deal.pre(lambda _: len(_.fractions) >= 2)
@deal.pre(lambda _: _.fractions[-1][1] is None)
@deal.ensure(lambda _: len(_.result) == len(_.fractions))
def _scale_to_watts(
    ftp: int, fractions: Sequence[tuple[str, float | None]]
) -> tuple[_ZoneBounds, ...]:
    """Scale a table of FTP fractions to absolute watt bounds.

    Args:
        ftp: Functional threshold power in watts.
        fractions: Zone names with their upper bound as a fraction of FTP,
            ascending, the last one open-ended (``None``).

    Returns:
        The zones as contiguous watt intervals, ascending.
    """
    bounds: list[_ZoneBounds] = []
    lower = 0.0
    for name, fraction in fractions:
        upper = None if fraction is None else fraction * ftp
        bounds.append(_ZoneBounds(name=name, lower=lower, upper=upper))
        lower = upper if upper is not None else lower
    return tuple(bounds)


@deal.pre(lambda _: len(_.upper_edges) >= 1)
@deal.pre(lambda _: all(lower < upper for lower, upper in pairwise(_.upper_edges)))
@deal.ensure(lambda _: len(_.result) == len(_.upper_edges) + 1)
@deal.ensure(lambda _: all(duration >= timedelta(0) for duration in _.result))
def _accumulate_zone_durations(
    samples: Sequence[tuple[datetime, float]], upper_edges: Sequence[float]
) -> list[timedelta]:
    """Sum the moving time each sample pair spends in its zone.

    Each interval is attributed to the zone of its earlier sample, which is
    the same convention the heart-rate analysis uses.

    Args:
        samples: Timestamped power values, ordered by time.
        upper_edges: Inclusive upper watt bounds of all zones except the
            open-ended top one, strictly ascending.

    Returns:
        One duration per zone, in ascending zone order.
    """
    durations = [timedelta(0)] * (len(upper_edges) + 1)
    for (earlier_time, earlier_power), (later_time, _later_power) in pairwise(samples):
        gap = later_time - earlier_time
        if gap > PAUSE_GAP_THRESHOLD:
            continue
        durations[bisect_left(upper_edges, earlier_power)] += gap
    return durations


@deal.pre(lambda _: _.ftp is None or _.ftp > 0)
@deal.ensure(lambda _: _.result is None or _.result.zone_model is _.zone_model)
@deal.ensure(
    lambda _: (
        _.result is None
        or [zone.index for zone in _.result.zones]
        == list(range(1, len(_.result.zones) + 1))
    )
)
@deal.ensure(lambda _: _.result is None or _.result.total_duration >= timedelta(0))
def power_zone_distribution(
    records: list[RecordPoint],
    ftp: int | None,
    zone_model: PowerZoneModel = DEFAULT_POWER_ZONE_MODEL,
) -> PowerZoneDistribution | None:
    """Compute the time spent in each power zone of a ride.

    Records without a power reading are ignored; gaps longer than
    ``PAUSE_GAP_THRESHOLD`` count as paused and are attributed to no zone.

    Args:
        records: The ride's record points, ordered by timestamp.
        ftp: Functional threshold power in watts, or ``None`` if unknown.
        zone_model: Which zone definition to use. Defaults to the seven-zone
            Coggan model.

    Returns:
        The zone distribution, or ``None`` if the FTP is unknown or fewer
        than two records carry a power reading.
    """
    if ftp is None:
        return None

    samples = [(r.timestamp, float(r.power)) for r in records if r.power is not None]
    if len(samples) < 2:
        return None

    bounds = _scale_to_watts(ftp, _ZONE_FRACTIONS[zone_model])
    upper_edges = [zone.upper for zone in bounds if zone.upper is not None]
    durations = _accumulate_zone_durations(samples, upper_edges)

    return PowerZoneDistribution(
        zone_model=zone_model,
        ftp=ftp,
        zones=tuple(
            PowerZone(
                index=index,
                name=zone.name,
                lower_bound=zone.lower,
                upper_bound=zone.upper,
                duration=duration,
            )
            for index, (zone, duration) in enumerate(
                zip(bounds, durations, strict=True), start=1
            )
        ),
    )
