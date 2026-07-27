"""Generic numeric computation behind the workout metrics."""

import math
from collections.abc import Sequence

import deal


def _is_between(result: float, low: float, high: float) -> bool:
    """Check whether ``result`` lies within ``[low, high]``.

    A value that only misses a bound due to floating-point rounding still
    counts as within it: summing and dividing floats does not always
    reproduce a boundary value exactly, even where real-number arithmetic
    would.

    Args:
        result: The value to check.
        low: Lower bound, inclusive up to floating-point rounding.
        high: Upper bound, inclusive up to floating-point rounding.

    Returns:
        True if ``result`` is within the bounds, or close enough to one of
        them to count as equal.

    >>> _is_between(150.0, 140.0, 160.0)
    True
    >>> _is_between(699051.2972669775, 699051.2972669776, 699051.2972669776)
    True
    >>> _is_between(130.0, 140.0, 160.0)
    False
    """
    return (
        low <= result <= high or math.isclose(result, low) or math.isclose(result, high)
    )


@deal.pre(lambda numbers: len(numbers) > 0)
@deal.ensure(lambda _: _is_between(_.result, min(_.numbers), max(_.numbers)))
def average(numbers: Sequence[float]) -> float:
    """Compute the arithmetic mean of a non-empty list of numbers.

    Args:
        numbers: The numbers to average; must not be empty.

    Returns:
        The arithmetic mean, which always lies between the minimum and
        maximum of ``numbers`` (up to floating-point rounding).

    Raises:
        deal.PreContractError: If ``numbers`` is empty.

    >>> average([140, 150, 160])
    150.0
    """
    return sum(numbers) / len(numbers)
