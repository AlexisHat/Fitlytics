"""The shared green-to-red colour scale for training-load intensity."""

from itertools import pairwise
from typing import Final

IntensityStop = tuple[int, tuple[int, int, int]]

INTENSITY_STOPS: Final[tuple[IntensityStop, ...]] = (
    (0, (187, 247, 208)),  # green-200 — light effort
    (25, (74, 222, 128)),  # green-400
    (50, (250, 204, 21)),  # yellow-400
    (75, (251, 146, 60)),  # orange-400
    (100, (220, 38, 38)),  # red-600 — hardest effort
)
"""Colour stops for the 0-100 intensity scale: green through yellow and
orange to red. A hue progression separates mid-range values far better than
a single-hue lightness ramp, where e.g. 40% and 60% intensity looked almost
identical — see docs/entscheidungen.md.

Shared by the calendar's day tiles and the recovery chart's workout markers,
so the same effort carries the same colour wherever it is shown."""


def intensity_rgb(pct: int) -> tuple[int, int, int]:
    """Interpolate an RGB colour for a 0-100 intensity along ``INTENSITY_STOPS``.

    Args:
        pct: The intensity to colour, 0 to 100.

    Returns:
        The interpolated colour as an ``(r, g, b)`` triple, each 0-255.

    Raises:
        AssertionError: If ``pct`` lies outside 0-100.

    >>> intensity_rgb(0)
    (187, 247, 208)
    >>> intensity_rgb(50)
    (250, 204, 21)
    >>> intensity_rgb(100)
    (220, 38, 38)
    """
    for (lo_pct, lo_rgb), (hi_pct, hi_rgb) in pairwise(INTENSITY_STOPS):
        if lo_pct <= pct <= hi_pct:
            fraction = (pct - lo_pct) / (hi_pct - lo_pct)
            lo_r, lo_g, lo_b = lo_rgb
            hi_r, hi_g, hi_b = hi_rgb
            return (
                round(lo_r + (hi_r - lo_r) * fraction),
                round(lo_g + (hi_g - lo_g) * fraction),
                round(lo_b + (hi_b - lo_b) * fraction),
            )
    raise AssertionError(f"pct {pct} outside the range INTENSITY_STOPS covers")


def intensity_color(pct: int) -> str:
    """Format the interpolated intensity colour as a CSS hex string.

    Args:
        pct: The intensity to colour, 0 to 100.

    Returns:
        The colour as ``#rrggbb``, understood by both matplotlib and CSS.

    Raises:
        AssertionError: If ``pct`` lies outside 0-100.

    >>> intensity_color(0)
    '#bbf7d0'
    >>> intensity_color(100)
    '#dc2626'
    """
    return "#{:02x}{:02x}{:02x}".format(*intensity_rgb(pct))
