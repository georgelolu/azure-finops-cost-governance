"""Read-only validation for daily Azure Cost Management exports."""

import argparse
import csv
import gzip
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_COLUMNS = {
    "date",
    "billingCurrency",
    "costInBillingCurrency",
    "tags",
}


def utc_now():
    return datetime.now(timezone.utc)


def validate_gzip_csv(path):
    """Check compressed CSV integrity, schema, and basic record validity."""
    record_count = 0
    currencies = set()

    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))

        if missing:
            raise ValueError(
                "Missing required columns: " + ", ".join(missing)
            )

        for line_number, row in enumerate(reader, start=2):
            if not row or not any(
                value not in (None, "") for value in row.values()
            ):
                continue

            if not (row.get("date") or "").strip():
                raise ValueError(f"Row {line_number} has no date.")

            currency = (row.get("billingCurrency") or "").strip()
            if not currency:
                raise ValueError(f"Row {line_number} has no billing currency.")

            try:
                cost = float((row.get("costInBillingCurrency") or "").strip())
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Row {line_number} has an invalid cost value."
                ) from exc

            if not math.isfinite(cost):
                raise ValueError(
                    f"Row {line_number} has a non-finite cost value."
                )

            currencies.add(currency.upper())
            record_count += 1

    if record_count == 0:
        raise ValueError("Export contains no billing records.")

    return {
        "record_count": record_count,
        "currencies": sorted(currencies),
    }


def result_for_file(path, modified_at, max_age_hours, source):
    """Validate a file and return a summary without exposing billing rows."""
    now = utc_now()

    if modified_at.tzinfo is None:
        modified_at = modified_at.replace(tzinfo=timezone.utc)

    modified_at = modified_at.astimezone(timezone.utc)
    age_hours = max(0, (now - modified_at).total_seconds() / 3600)

    result = {
        "status": "valid",
        "source": source,
        "checked_at_utc": now.isoformat(),
        "export_modified_at_utc": modified_at.isoformat(),
        "export_age_hours": round(age_hours, 2),
        "max_age_hours": max_age_hours,
    }

    try:
        result.update(validate_gzip_csv(path))
    except (OSError, EOFError, UnicodeError, csv.Error, ValueError) as exc:
        result.update({
            "status": "invalid_export",
            "error": str(exc),
        })
        return result

    if age_hours > max_age_hours:
        result.update({
            "status": "stale_export",
            "error": "Export is older than the configured freshness limit.",
        })

    return result


def validate_local_file(path, max_age_hours):
    """Validate a downloaded export for local testing."""
    path = Path(path)

    if not path.is_file():
        return {
            "status": "missing_export",
            "source": "local_file",
            "error": "The specified export file does not exist.",
        }

    modified_at = datetime.fromtimestamp(
        path.stat().st_mtime, timezone.utc
    )
    return result_for_file(
        path, modified_at, max_age_hours, "local_file"
    )


def validate_latest_blob(max_age_hours):
    """Find and validate the latest matching Azure Blob export."""
    account_url = os.environ.get("AZURE_STORAGE_ACCOUNT_URL", "").strip()
    container_name = os.environ.get(
        "AZURE_STORAGE_CONTAINER", "cost-exports"
    ).strip()
    prefix = os.environ.get(
        "AZURE_EXPORT_PREFIX",
        "daily/finops-daily-cost-export/",
    ).strip().lstrip("/")

    if not account_url:
        raise ValueError(
            "AZURE_STORAGE_ACCOUNT_URL must contain your Blob Storage URL."
        )

    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    credential = DefaultAzureCredential()

    try:
        service = BlobServiceClient(
            account_url=account_url,
            credential=credential,
        )
        container = service.get_container_client(container_name)

        candidates = [
            blob
            for blob in container.list_blobs(name_starts_with=prefix)
            if blob.name.lower().endswith(".csv.gz")
        ]

        if not candidates:
            return {
                "status": "missing_export",
                "source": "azure_blob",
                "checked_at_utc": utc_now().isoformat(),
                "error": "No compressed CSV export found under the prefix.",
            }

        latest = max(
            candidates,
            key=lambda blob: blob.last_modified
            or datetime.min.replace(tzinfo=timezone.utc),
        )

        if latest.last_modified is None:
            raise ValueError("Latest export has no modification timestamp.")

        # Stream to a temporary file rather than loading the entire export
        # into memory. The temporary file is deleted automatically.
        with tempfile.TemporaryDirectory(
            prefix="finops-export-check-"
        ) as temp_dir:
            local_path = Path(temp_dir) / "export.csv.gz"

            with local_path.open("wb") as destination:
                container.download_blob(latest.name).readinto(destination)

            return result_for_file(
                local_path,
                latest.last_modified,
                max_age_hours,
                "azure_blob",
            )
    finally:
        credential.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only Azure Cost Management export validation."
    )
    parser.add_argument(
        "--input",
        help="Validate a local .csv.gz file instead of querying Azure.",
    )
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=48,
        help="Maximum allowed export age in hours (default: 48).",
    )
    args = parser.parse_args(argv)

    if not math.isfinite(args.max_age_hours) or args.max_age_hours <= 0:
        parser.error("--max-age-hours must be a positive finite number.")

    try:
        if args.input:
            result = validate_local_file(args.input, args.max_age_hours)
        else:
            result = validate_latest_blob(args.max_age_hours)
    except Exception as exc:
        # Fail closed: auth, configuration, and network errors are failures.
        result = {
            "status": "validation_error",
            "source": "azure_blob",
            "checked_at_utc": utc_now().isoformat(),
            "error": f"{type(exc).__name__}: {exc}",
        }

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "valid" else 1


if __name__ == "__main__":
    sys.exit(main())
