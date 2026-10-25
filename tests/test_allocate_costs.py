import pandas as pd
import pytest

from finops.allocate_costs import load_costs, build_reports


def test_sample_costs_are_allocated_and_summarized(tmp_path):
    df = load_costs("data/sample/costs.csv")
    result = build_reports(df, tmp_path)

    assert result["record_count"] == 6
    assert result["total_cost"] == 68.0
    assert result["unallocated_cost"] == 5.0
    assert result["unallocated_percentage"] == 7.35

    projects = pd.read_csv(tmp_path / "cost_by_project.csv")
    totals = projects.groupby("project")["cost"].sum().to_dict()

    assert totals["finops-platform"] == 37.0
    assert totals["commerce"] == 26.0
    assert totals["unallocated"] == 5.0


def test_missing_required_column_fails(tmp_path):
    path = tmp_path / "invalid.csv"
    path.write_text("date,project,cost\n2026-10-01,app,10\n")

    with pytest.raises(ValueError, match="Missing required columns"):
        load_costs(path)


def test_invalid_date_fails(tmp_path):
    path = tmp_path / "invalid_date.csv"
    path.write_text(
        "date,project,environment,team,service,cost,source\n"
        "not-a-date,app,dev,platform,compute,10,simulated\n"
    )

    with pytest.raises(ValueError, match="Invalid or missing date"):
        load_costs(path)


def test_negative_cost_is_preserved_as_adjustment(tmp_path):
    path = tmp_path / "credit.csv"
    path.write_text(
        "date,project,environment,team,service,cost,source,currency\n"
        "2026-10-01,app,dev,platform,compute,10,azure_cost_export_actual,USD\n"
        "2026-10-01,app,dev,platform,compute,-3,azure_cost_export_actual,USD\n"
    )

    df = load_costs(path)
    assert df["cost"].tolist() == [10, -3]

    result = build_reports(df, tmp_path / "reports")
    assert result["total_cost"] == 7.0

    summary = pd.read_csv(tmp_path / "reports" / "summary.csv")
    assert summary.loc[0, "total_cost"] == 7.0
    assert summary.loc[0, "absolute_cost_amount"] == 13.0
