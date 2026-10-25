import csv
import gzip
from datetime import datetime, timedelta, timezone

import pytest

from finops.validate_azure_export import (
    result_for_file,
    validate_gzip_csv,
    validate_local_file,
)

COLUMNS = [
    "date",
    "billingCurrency",
    "costInBillingCurrency",
    "tags",
]


def make_export(path, rows=None, columns=None):
    columns = columns or COLUMNS
    rows = rows if rows is not None else [
        {
            "date": "2026-10-24",
            "billingCurrency": "USD",
            "costInBillingCurrency": "1.25",
            "tags": "{}",
        }
    ]

    with gzip.open(path, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    return path


def test_valid_export_reports_record_count_and_currency(tmp_path):
    path = make_export(tmp_path / "valid.csv.gz")

    result = validate_gzip_csv(path)

    assert result["record_count"] == 1
    assert result["currencies"] == ["USD"]


def test_missing_required_column_is_rejected(tmp_path):
    path = make_export(
        tmp_path / "missing-column.csv.gz",
        columns=["date", "billingCurrency", "tags"],
        rows=[{
            "date": "2026-10-24",
            "billingCurrency": "USD",
            "tags": "{}",
        }],
    )

    with pytest.raises(ValueError, match="Missing required columns"):
        validate_gzip_csv(path)


def test_invalid_cost_is_rejected(tmp_path):
    path = make_export(
        tmp_path / "invalid-cost.csv.gz",
        rows=[{
            "date": "2026-10-24",
            "billingCurrency": "USD",
            "costInBillingCurrency": "not-a-number",
            "tags": "{}",
        }],
    )

    with pytest.raises(ValueError, match="invalid cost"):
        validate_gzip_csv(path)


def test_empty_export_is_rejected(tmp_path):
    path = make_export(tmp_path / "empty.csv.gz", rows=[])

    with pytest.raises(ValueError, match="no billing records"):
        validate_gzip_csv(path)


def test_corrupt_gzip_is_reported_as_invalid(tmp_path):
    path = tmp_path / "corrupt.csv.gz"
    path.write_bytes(b"this is not a gzip file")

    result = result_for_file(
        path,
        datetime.now(timezone.utc),
        48,
        "local_file",
    )

    assert result["status"] == "invalid_export"


def test_stale_export_is_reported(tmp_path):
    path = make_export(tmp_path / "stale.csv.gz")
    old_timestamp = datetime.now(timezone.utc) - timedelta(hours=72)

    result = result_for_file(path, old_timestamp, 48, "local_file")

    assert result["status"] == "stale_export"


def test_missing_local_export_is_reported(tmp_path):
    result = validate_local_file(tmp_path / "does-not-exist.csv.gz", 48)

    assert result["status"] == "missing_export"


def test_negative_cost_adjustment_is_valid(tmp_path):
    path = make_export(
        tmp_path / "credit.csv.gz",
        rows=[{
            "date": "2026-10-24",
            "billingCurrency": "USD",
            "costInBillingCurrency": "-0.50",
            "tags": "{}",
        }],
    )

    assert validate_gzip_csv(path)["record_count"] == 1
