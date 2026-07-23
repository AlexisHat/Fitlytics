"""Tests for the errors package."""

import pytest

from errors import (
    AnalysisError,
    DataValidationError,
    FileImportError,
    FitlyticsError,
    StorageError,
)


@pytest.mark.parametrize(
    "exc_type",
    [FileImportError, DataValidationError, StorageError, AnalysisError],
)
def test_all_custom_errors_are_fitlytics_errors(exc_type: type[FitlyticsError]) -> None:
    assert issubclass(exc_type, FitlyticsError)


def test_fitlytics_error_carries_message() -> None:
    with pytest.raises(FileImportError, match="corrupt FIT file"):
        raise FileImportError("corrupt FIT file")
