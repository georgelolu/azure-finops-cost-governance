import pandas as pd

from finops.allocate_costs import load_costs, build_reports


def write_cost_file(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_mixed_currencies_are_never_combined(tmp_path):
    path = write_cost_file(
        tmp_path / "mixed.csv",
        [
            {
                "date": "2026-10-01", "project": "app",
                "environment": "dev", "team": "platform",
                "service": "compute", "cost": 10,
                "source": "azure_cost_export_actual", "currency": "USD",
            },
            {
                "date": "2026-10-01", "project": "app",
                "environment": "dev", "team": "platform",
                "service": "compute", "cost": 20,
                "source": "azure_cost_export_actual", "currency": "EUR",
            },
        ],
    )

    df = load_costs(path)
    result = build_reports(df, tmp_path / "reports")

    assert result["currency_count"] == 2
    assert result["total_cost"] is None
    assert result["total_cost_by_currency"] == {"EUR": 20.0, "USD": 10.0}

    summary = pd.read_csv(tmp_path / "reports" / "summary.csv")
    totals = dict(zip(summary["currency"], summary["total_cost"]))
    assert totals == {"EUR": 20.0, "USD": 10.0}

    daily = pd.read_csv(tmp_path / "reports" / "daily_costs.csv")
    assert len(daily) == 2
    assert set(daily["currency"]) == {"USD", "EUR"}


def test_credits_do_not_hide_unallocated_cost_coverage(tmp_path):
    path = write_cost_file(
        tmp_path / "credits.csv",
        [
            {
                "date": "2026-10-01", "project": "app",
                "environment": "dev", "team": "platform",
                "service": "compute", "cost": 100,
                "source": "azure_cost_export_actual", "currency": "USD",
            },
            {
                "date": "2026-10-01", "project": "unallocated",
                "environment": "unknown", "team": "unallocated",
                "service": "compute", "cost": -20,
                "source": "azure_cost_export_actual", "currency": "USD",
                "charge_type": "Adjustment",
            },
        ],
    )

    df = load_costs(path)
    result = build_reports(df, tmp_path / "reports")

    assert result["total_cost"] == 80.0
    assert result["unallocated_cost"] == -20.0

    summary = pd.read_csv(tmp_path / "reports" / "summary.csv")
    row = summary.iloc[0]

    assert row["record_count"] == 2
    assert row["unallocated_record_count"] == 1
    assert row["unallocated_record_percentage"] == 50.0
    assert row["absolute_cost_amount"] == 120.0
    assert row["unallocated_absolute_cost"] == 20.0
    assert row["unallocated_cost_percentage"] == 16.67


def test_missing_currency_is_labeled_unknown(tmp_path):
    path = write_cost_file(
        tmp_path / "no_currency.csv",
        [{
            "date": "2026-10-01", "project": "app",
            "environment": "dev", "team": "platform",
            "service": "compute", "cost": 5,
            "source": "simulated",
        }],
    )

    df = load_costs(path)
    assert df.loc[0, "currency"] == "UNKNOWN"


def test_dimension_coverage_is_reported_independently(tmp_path):
    path = write_cost_file(
        tmp_path / "dimension_coverage.csv",
        [
            {
                "date": "2026-10-01",
                "project": "pet-clinic-aks",
                "environment": "dev",
                "team": "platform",
                "service": "compute",
                "cost": 80,
                "source": "azure_cost_export_actual",
                "currency": "USD",
            },
            {
                "date": "2026-10-01",
                "project": "pet-clinic-aks",
                "environment": "unknown",
                "team": "unallocated",
                "service": "compute",
                "cost": 20,
                "source": "azure_cost_export_actual",
                "currency": "USD",
            },
        ],
    )

    df = load_costs(path)
    build_reports(df, tmp_path / "coverage_reports")

    summary = pd.read_csv(
        tmp_path / "coverage_reports" / "summary.csv"
    ).iloc[0]

    assert summary["project_covered_record_percentage"] == 100.0
    assert summary["project_covered_cost_percentage"] == 100.0
    assert summary["environment_covered_record_percentage"] == 50.0
    assert summary["environment_covered_cost_percentage"] == 80.0
    assert summary["team_covered_record_percentage"] == 50.0
    assert summary["team_covered_cost_percentage"] == 80.0
    assert summary["service_covered_record_percentage"] == 100.0
    assert summary["service_covered_cost_percentage"] == 100.0
    assert summary["unallocated_cost_percentage"] == 20.0
