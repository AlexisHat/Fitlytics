"""Exception hierarchy for Fitlytics.

Foreign exceptions from fitdecode, polars, sqlite3 and file IO are caught at the
module boundary and re-raised as one of these, so calling code only ever needs
to handle ``FitlyticsError``.
"""


class FitlyticsError(Exception):
    """Base class for all Fitlytics-specific errors."""


class FileImportError(FitlyticsError):
    """Raised when a FIT or CSV file cannot be read or parsed."""


class DataValidationError(FitlyticsError):
    """Raised when imported data violates a required invariant."""


class StorageError(FitlyticsError):
    """Raised when reading from or writing to the SQLite database fails."""


class AnalysisError(FitlyticsError):
    """Raised when computing metrics or interval analysis fails."""
