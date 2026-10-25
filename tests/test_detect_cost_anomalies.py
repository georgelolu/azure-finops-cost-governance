import json

import pandas as pd
import pytest

from finops.detect_cost_anomalies import run_detection


def make_costs(rows, path):
    columns = [
        "date", "project", "environment", "service",
        "cost", "currency", "source",
    ]
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)
    return path


def row(date, cost, source="simulated", currency="USD",
        project="demo", environment="dev", service="compute"):
    return [date, project, environment, service, cost, currency, source]


def detect(tmp_path, rows, **options):
    input_path = make_costs(rows, tmp_path / "costs.csv")
    output_dir = tmp_path / "reports"
    summary = run_detection(input_path, output_dir, **options)
    anomalies = pd.read_csv(output_dir / "cost_anomalies.csv")
    return summary, anomalies


def test_detects_large_spending_spike(tmp_path):
    rows = [
        row("2026-10-01", 10),
        row("2026-10-02", 10),
        row("2026-10-03", 10),
        row("2026-10-04", 40),
    ]
    summary, anomalies = detect(
        tmp_path, rows, min_baseline_days=3
    )

    assert summary["anomaly_count"] == 1
    assert anomalies.iloc[0]["date"] == "2026-10-04"
    assert anomalies.iloc[0]["baseline_median_cost"] == pytest.approx(10)
    assert anomalies.iloc[0]["observed_cost"] == pytest.approx(40)


def test_negative_credit_is_not_a_spending_spike(tmp_path):
    rows = [
        row("2026-10-01", 10),
        row("2026-10-02", 10),
        row("2026-10-03", -20),
    ]
    summary, _ = detect(tmp_path, rows, min_baseline_days=2)
    assert summary["anomaly_count"] == 0


def test_missing_calendar_day_is_not_fabricated(tmp_path):
    rows = [
        row("2026-10-01", 10),
        row("2026-10-02", 10),
        # October 3 is absent from the entire export.
        row("2026-10-04", 100),
    ]
    summary, anomalies = detect(
        tmp_path, rows, min_baseline_days=2
    )

    assert summary["anomaly_count"] == 1
    assert anomalies.iloc[0]["baseline_days"] == 2


def test_insufficient_history_does_not_flag_spike(tmp_path):
    rows = [
        row("2026-10-01", 10),
        row("2026-10-03", 100),
    ]
    summary, anomalies = detect(
        tmp_path, rows, min_baseline_days=2
    )

    assert summary["anomaly_count"] == 0
    assert summary["insufficient_history_group_days"] > 0
    assert anomalies.empty


def test_small_increase_is_filtered_by_absolute_threshold(tmp_path):
    rows = [
        row("2026-10-01", 5),
        row("2026-10-02", 5),
        row("2026-10-03", 6),
    ]
    summary, _ = detect(
        tmp_path, rows,
        min_baseline_days=2,
        min_cost=5,
        min_increase=5,
    )
    assert summary["anomaly_count"] == 0


def test_sources_and_currencies_are_not_combined(tmp_path):
    rows = [
        row("2026-10-01", 10, "simulated", "USD"),
        row("2026-10-02", 10, "simulated", "USD"),
        row("2026-10-03", 40, "simulated", "USD"),
        row("2026-10-01", 100, "actual", "EUR"),
        row("2026-10-02", 100, "actual", "EUR"),
        row("2026-10-03", 100, "actual", "EUR"),
    ]
    summary, anomalies = detect(
        tmp_path, rows, min_baseline_days=2
    )

    assert summary["anomaly_count"] == 1
    assert anomalies.iloc[0]["source"] == "simulated"
    assert anomalies.iloc[0]["currency"] == "USD"


def test_invalid_cost_is_rejected(tmp_path):
    input_path = tmp_path / "costs.csv"
    input_path.write_text(
        "date,project,environment,service,cost,source\n"
        "2026-10-01,demo,dev,compute,not-a-number,simulated\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid or non-finite costs"):
        run_detection(input_path, tmp_path / "reports")


def test_summary_does_not_publish_billing_totals(tmp_path):
    rows = [
        row("2026-10-01", 10),
        row("2026-10-02", 10),
    ]
    _, _ = detect(tmp_path, rows, min_baseline_days=1)
    summary = json.loads(
        (tmp_path / "reports" / "anomaly_summary.json").read_text()
    )

    assert "total_cost" not in summary
    assert "total_spend" not in summary
    assert summary["status"] == "completed"
