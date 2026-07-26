"""Report of the measurements discarded while validating imported data."""

from pydantic import BaseModel, ConfigDict, Field


class ValidationReport(BaseModel):
    """How many implausible values validation discarded, per field.

    Dropping a value without saying so would be a silent fallback: the
    average heart rate would quietly improve and nothing would explain why.
    Validation therefore returns this alongside the cleaned data, so the
    user interface can show what was thrown away.

    Attributes:
        discarded: Number of discarded values per field name. Fields from
            which nothing was discarded are absent.
    """

    model_config = ConfigDict(frozen=True)

    discarded: dict[str, int] = Field(default_factory=dict)

    @property
    def total(self) -> int:
        """Total number of discarded values across all fields.

        Returns:
            The sum of all per-field counts.

        >>> ValidationReport(discarded={"heart_rate": 3, "power": 1}).total
        4
        >>> ValidationReport().total
        0
        """
        return sum(self.discarded.values())

    @property
    def is_clean(self) -> bool:
        """Whether every imported value survived validation.

        Returns:
            True if nothing was discarded.

        >>> ValidationReport().is_clean
        True
        >>> ValidationReport(discarded={"power": 1}).is_clean
        False
        """
        return not self.discarded

    def summary(self) -> str:
        """Describe the discarded values in one line, for display to the user.

        Returns:
            A human-readable summary, listing fields alphabetically.

        >>> ValidationReport(discarded={"power": 1, "heart_rate": 3}).summary()
        'discarded implausible values: 3 heart_rate values, 1 power value'
        >>> ValidationReport().summary()
        'no implausible values found'
        """
        if not self.discarded:
            return "no implausible values found"

        parts = [
            f"{count} {name} value{'' if count == 1 else 's'}"
            for name, count in sorted(self.discarded.items())
        ]
        return f"discarded implausible values: {', '.join(parts)}"
