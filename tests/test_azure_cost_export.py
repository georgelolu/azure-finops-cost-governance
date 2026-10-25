import csv
import gzip
import json

from finops.connectors.azure_cost_export import (
    normalize_export,
    normalize_row,
)


def test_explicit_tags_are_used_for_allocation():
    row = {
        "date": "2026-10-01",
        "billingCurrency": "USD",
        "costInBillingCurrency": "12.50",
        "tags": json.dumps({
            "project": "test-app",
            "environment": "dev",
            "team": "platform",
        }),
        "resourceGroupName": "rg-test",
        "consumedService": "Microsoft.Compute",
        "costInUsd": "12.50",
        "costInPricingCurrency": "12.50",
        "SubscriptionId": "synthetic-subscription",
        "ResourceId": "/synthetic/resource",
        "chargeType": "Usage",
        "serviceFamily": "Compute",
        "meterCategory": "Virtual Machines",
        "costCenter": "CC-TEST",
    }

    result = normalize_row(row)

    assert result["project"] == "test-app"
    assert result["environment"] == "dev"
    assert result["team"] == "platform"
    assert result["source"] == "azure_cost_export_actual"
    assert result["cost_type"] == "actual"
    assert result["project_allocation_method"] == "explicit_tag"
    assert result["environment_allocation_method"] == "explicit_tag"
    assert result["team_allocation_method"] == "explicit_tag"


def test_resource_group_is_not_used_as_project_fallback():
    row = {
        "date": "2026-10-01",
        "billingCurrency": "USD",
        "costInBillingCurrency": "8.00",
        "tags": "{}",
        "resourceGroupName": "rg-production",
        "consumedService": "Microsoft.Compute",
    }

    result = normalize_row(row)

    assert result["project"] == "unallocated"
    assert result["environment"] == "unknown"
    assert result["team"] == "unallocated"
    assert result["project_allocation_method"] == "unallocated"
    assert result["environment_allocation_method"] == "unknown"
    assert result["team_allocation_method"] == "unallocated"


def test_gzip_export_is_normalized(tmp_path):
    input_path = tmp_path / "synthetic_cost_export.csv.gz"
    output_path = tmp_path / "normalized_costs.csv"

    fields = [
        "date",
        "billingCurrency",
        "costInBillingCurrency",
        "tags",
        "resourceGroupName",
        "consumedService",
    ]

    synthetic_rows = [
        {
            "date": "2026-10-01",
            "billingCurrency": "USD",
            "costInBillingCurrency": "12.50",
            "tags": json.dumps({
                "project": "test-app",
                "environment": "dev",
                "team": "platform",
            }),
            "resourceGroupName": "rg-test",
            "consumedService": "Microsoft.Compute",
        },
        {
            "date": "2026-10-02",
            "billingCurrency": "USD",
            "costInBillingCurrency": "8.00",
            "tags": "{}",
            "resourceGroupName": "rg-production",
            "consumedService": "Microsoft.Storage",
        },
    ]

    with gzip.open(input_path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(synthetic_rows)

    normalize_export(input_path, output_path)

    with output_path.open(encoding="utf-8", newline="") as file:
        results = list(csv.DictReader(file))

    assert len(results) == 2
    assert results[0]["project"] == "test-app"
    assert results[1]["project"] == "unallocated"
    assert all(
        row["source"] == "azure_cost_export_actual"
        for row in results
    )
    assert all(row["cost_type"] == "actual" for row in results)
