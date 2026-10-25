"""Normalize Azure Cost Management exports into FinOps records."""

import argparse
import csv
import gzip
import json
import math
from pathlib import Path


REQUIRED_AZURE_COLUMNS = {
    "date",
    "billingCurrency",
    "costInBillingCurrency",
    "tags",
}

OUTPUT_COLUMNS = [
    "date", "project", "environment", "team", "service", "cost",
    "source", "currency", "cost_type", "subscription_id",
    "resource_group", "resource_id", "charge_type", "service_family",
    "meter_category", "cost_in_usd", "cost_in_pricing_currency",
    "cost_center", "project_allocation_method",
    "environment_allocation_method", "team_allocation_method",
    "allocation_basis",
]


def parse_tags(raw_tags):
    """Parse Azure's JSON-formatted resource tags safely."""
    if not raw_tags:
        return {}

    try:
        tags = json.loads(raw_tags)
    except (json.JSONDecodeError, TypeError):
        return {}

    if not isinstance(tags, dict):
        return {}

    return {
        str(key).strip().lower().replace(" ", "_"): value
        for key, value in tags.items()
    }


def first_value(*values, default=""):
    """Return the first non-empty value."""
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def load_resource_group_mapping(mapping_path):
    """Load mappings keyed by lowercase resource-group name."""
    if mapping_path is None:
        return {}

    path = Path(mapping_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Resource-group mapping file not found: {path}"
        )

    mappings = {}
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {
            "resource_group", "project", "environment", "team",
            "cost_center", "allocation_basis",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                "Mapping file is missing columns: "
                + ", ".join(sorted(missing))
            )

        for row in reader:
            name = first_value(row.get("resource_group")).lower()
            if not name:
                continue
            if name in mappings:
                raise ValueError(
                    f"Duplicate resource-group mapping: {name}"
                )
            mappings[name] = {
                key: first_value(row.get(key))
                for key in required
                if key != "resource_group"
            }

    return mappings


def normalize_row(row, resource_group_mapping=None):
    """Normalize one Azure cost row, preferring explicit row tags."""
    tags = parse_tags(row.get("tags"))
    resource_group = first_value(row.get("resourceGroupName"))
    mapping = (resource_group_mapping or {}).get(
        resource_group.lower(), {}
    )

    date = first_value(row.get("date"))
    raw_cost = first_value(row.get("costInBillingCurrency"))

    if not date:
        raise ValueError("Azure export contains a row without a date.")

    try:
        cost = float(raw_cost)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Azure export contains a missing or invalid "
            "costInBillingCurrency value."
        ) from exc

    if not math.isfinite(cost):
        raise ValueError("Azure export contains a non-finite cost.")

    # Explicit cost-row tags always win over the mapping fallback.
    project_tag = first_value(
        tags.get("project"), tags.get("application"), tags.get("app")
    )
    environment_tag = first_value(
        tags.get("environment"), tags.get("env")
    )
    team_tag = first_value(tags.get("team"), tags.get("owner_team"))

    project = project_tag or first_value(
        mapping.get("project"), default="unallocated"
    )
    environment = environment_tag or first_value(
        mapping.get("environment"), default="unknown"
    )
    team = team_tag or first_value(
        mapping.get("team"), default="unallocated"
    )

    project_method = (
        "explicit_tag" if project_tag else
        "resource_group_mapping"
        if project not in {"", "unallocated"} and mapping else
        "unallocated"
    )
    environment_method = (
        "explicit_tag" if environment_tag else
        "resource_group_mapping"
        if environment not in {"", "unknown"} and mapping else
        "unknown"
    )
    team_method = (
        "explicit_tag" if team_tag else
        "resource_group_mapping"
        if team not in {"", "unallocated"} and mapping else
        "unallocated"
    )

    service = first_value(
        row.get("consumedService"),
        row.get("serviceFamily"),
        row.get("meterCategory"),
        default="unknown",
    )

    cost_center = first_value(
        tags.get("cost_center"),
        row.get("costCenter"),
        mapping.get("cost_center"),
    )

    used_mapping = any(
        method == "resource_group_mapping"
        for method in (
            project_method, environment_method, team_method
        )
    )
    allocation_basis = (
        mapping.get("allocation_basis", "resource_group_mapping")
        if used_mapping else
        "explicit_cost_row_tags"
        if any((project_tag, environment_tag, team_tag)) else
        "unallocated_no_verified_mapping"
    )

    return {
        "date": date,
        "project": project or "unallocated",
        "environment": environment or "unknown",
        "team": team or "unallocated",
        "service": service,
        "cost": cost,
        "source": "azure_cost_export_actual",
        "currency": first_value(
            row.get("billingCurrency"), default="unknown"
        ),
        "cost_type": "actual",
        "subscription_id": row.get("SubscriptionId", ""),
        "resource_group": resource_group,
        "resource_id": row.get("ResourceId", ""),
        "charge_type": row.get("chargeType", ""),
        "service_family": row.get("serviceFamily", ""),
        "meter_category": row.get("meterCategory", ""),
        "cost_in_usd": row.get("costInUsd", ""),
        "cost_in_pricing_currency": row.get(
            "costInPricingCurrency", ""
        ),
        "cost_center": cost_center,
        "project_allocation_method": project_method,
        "environment_allocation_method": environment_method,
        "team_allocation_method": team_method,
        "allocation_basis": allocation_basis,
    }


def normalize_export(input_path, output_path, mapping_path=None):
    """Read a compressed Azure export and write normalized CSV."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.is_file():
        raise FileNotFoundError(
            f"Azure export file not found: {input_path}"
        )

    mapping = load_resource_group_mapping(mapping_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with gzip.open(
        input_path, "rt", encoding="utf-8-sig", newline=""
    ) as source:
        reader = csv.DictReader(source)
        missing = REQUIRED_AZURE_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                "Azure export is missing required columns: "
                + ", ".join(sorted(missing))
            )

        row_count = 0
        currencies = set()

        with output_path.open(
            "w", encoding="utf-8", newline=""
        ) as destination:
            writer = csv.DictWriter(
                destination,
                fieldnames=OUTPUT_COLUMNS,
                extrasaction="ignore",
            )
            writer.writeheader()

            for row in reader:
                normalized = normalize_row(row, mapping)
                writer.writerow(normalized)
                currencies.add(normalized["currency"])
                row_count += 1

    return {
        "rows_processed": row_count,
        "currency_count": len(currencies),
        "output_path": str(output_path),
        "mapping_count": len(mapping),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Normalize an Azure Cost Management CSV.GZ export."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--mapping",
        default="config/resource_group_mapping.csv",
        help="CSV mapping file; pass an empty string to disable it.",
    )
    args = parser.parse_args()

    mapping_path = args.mapping or None
    result = normalize_export(
        args.input, args.output, mapping_path
    )

    print("Azure Cost Export normalization completed.")
    print(f"Rows processed: {result['rows_processed']}")
    print(f"Distinct currencies: {result['currency_count']}")
    print(f"Resource-group mappings loaded: {result['mapping_count']}")
    print(f"Normalized file: {result['output_path']}")


if __name__ == "__main__":
    main()
