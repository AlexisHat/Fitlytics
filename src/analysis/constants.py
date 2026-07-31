"""Constants and shared vocabulary for the analysis package.

Centralised here rather than left in whichever module first needed them, so
every module reaches for the same value instead of accidentally redefining
its own copy — exactly what once went wrong with a stray, wrongly typed
local copy of ``PAUSE_GAP_THRESHOLD``.
"""

from datetime import timedelta
from enum import StrEnum
from typing import Final

PAUSE_GAP_THRESHOLD: Final = timedelta(seconds=2)
"""Records are 1s apart while a device is actively recording (seen in every
real workout file); a wider gap means recording stopped, whether from
auto-pause or lost signal. 2s sits safely between the two."""


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


DEFAULT_POWER_ZONE_MODEL: Final = PowerZoneModel.COGGAN_7
