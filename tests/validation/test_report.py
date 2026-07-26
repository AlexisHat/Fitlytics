"""Tests for validation.report."""

from validation import ValidationReport


def test_empty_report_is_clean() -> None:
    report = ValidationReport()

    assert report.is_clean
    assert report.total == 0
    assert report.summary() == "no implausible values found"


def test_report_totals_all_fields() -> None:
    report = ValidationReport(discarded={"heart_rate": 3, "power": 1})

    assert not report.is_clean
    assert report.total == 4


def test_report_summary_lists_fields_alphabetically_with_plural() -> None:
    report = ValidationReport(discarded={"power": 1, "heart_rate": 3})

    assert (
        report.summary()
        == "discarded implausible values: 3 heart_rate values, 1 power value"
    )
