"""Detect unusually high daily costs using a rolling median baseline."""

import argparse
import json
import math
from pathlib import Path
from statistics import median

import pandas as pd


DIMENSIONS = ("project", "environment", "service")
REQUIRED_COLUMNS = ("date", "cost", "source", *DIMENSIONS)

ANOMALY_COLUMNS = [
    "date",
    "source",
    "currency",
    "project",
    "environment",
    "service",
    "observed_cost",
    "baseline_median_cost",
    "increase_amount",
    "increase_ratio",
    "baseline_days",
]


def run_detection(
    input_path,
    output_dir,
    lookback_days=7,
    min_baseline_days=3,
    ratio_threshold=2.0,
    min_cost=5.0,
    min_increase=5.0,
):
    """Write a local anomaly CSV and a metadata-only JSON summary."""
    if lookback_days < 1 or min_baseline_days < 1:
        raise ValueError("Lookback and minimum baseline days must be positive.")
    if ratio_threshold <= 1:
        raise ValueError("ratio_threshold must be greater than 1.")
    if min_cost < 0 or min_increase < 0:
        raise ValueError("Minimum cost and increase cannot be negative.")

    df = pd.read_csv(input_path)
    missing = sorted(set(REQUIRED_COLUMNS) - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    if df.empty:
        raise ValueError("Input cost dataset contains no records.")

    parsed_dates = pd.to_datetime(df["date"], errors="coerce", utc=True)
    if parsed_dates.isna().any():
        raise ValueError("Input contains invalid or missing dates.")

    costs = pd.to_numeric(df["cost"], errors="coerce")
    if costs.isna().any() or not all(math.isfinite(v) for v in costs):
        raise ValueError("Input contains invalid or non-finite costs.")

    df["date"] = parsed_dates.dt.strftime("%Y-%m-%d")
    df["cost"] = costs.astype(float)

    for column in (*DIMENSIONS, "source"):
        df[column] = df[column].fillna("").astype(str).str.strip()
        df[column] = df[column].replace("", "unknown")

    if "currency" not in df.columns:
        df["currency"] = "UNKNOWN"
    df["currency"] = (
        df["currency"].fillna("").astype(str).str.strip().str.upper()
        .replace("", "UNKNOWN")
    )

    # Keep data sources, currencies, and attribution dimensions separate.
    keys = ["source", "currency", *DIMENSIONS, "date"]
    daily = (
        df.groupby(keys, dropna=False, as_index=False)["cost"]
        .sum()
    )

    anomalies = []
    evaluated = 0
    insufficient_history = 0

    bucket_keys = ["source", "currency"]
    for (source, currency), bucket in daily.groupby(
        bucket_keys, sort=True, dropna=False
    ):
        # A date is observed only if the export has at least one row for
        # this source/currency. Entirely missing dates are not invented.
        observed_dates = sorted(bucket["date"].unique())

        group_keys = list(DIMENSIONS)
        for dimension_values, group in bucket.groupby(
            group_keys, sort=True, dropna=False
        ):
            if not isinstance(dimension_values, tuple):
                dimension_values = (dimension_values,)

            daily_costs = dict(zip(group["date"], group["cost"]))

            for current_date in observed_dates:
                current_day = pd.Timestamp(current_date)
                baseline_dates = [
                    day for day in observed_dates
                    if 0 < (current_day - pd.Timestamp(day)).days
                    <= lookback_days
                ]

                if len(baseline_dates) < min_baseline_days:
                    insufficient_history += 1
                    continue

                # An absent dimension row on an otherwise observed date
                # represents zero for that dimension on that date.
                baseline_values = [
                    float(daily_costs.get(day, 0.0))
                    for day in baseline_dates
                ]
                baseline = float(median(baseline_values))
                observed = float(daily_costs.get(current_date, 0.0))
                evaluated += 1

                increase = observed - baseline

                # Credits and negative/zero net costs are never spending
                # spikes. A zero baseline uses the absolute safeguards.
                if observed <= 0:
                    continue
                if observed < min_cost or increase < min_increase:
                    continue
                if baseline > 0 and observed < baseline * ratio_threshold:
                    continue

                record = {
                    "date": current_date,
                    "source": source,
                    "currency": currency,
                    **dict(zip(DIMENSIONS, dimension_values)),
                    "observed_cost": observed,
                    "baseline_median_cost": baseline,
                    "increase_amount": increase,
                    "increase_ratio": (
                        observed / baseline if baseline > 0 else ""
                    ),
                    "baseline_days": len(baseline_dates),
                }
                anomalies.append(record)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    anomalies_path = output_dir / "cost_anomalies.csv"
    pd.DataFrame(anomalies, columns=ANOMALY_COLUMNS).to_csv(
        anomalies_path, index=False
    )

    summary = {
        "status": "completed",
        "input_record_count": int(len(df)),
        "anomaly_count": len(anomalies),
        "evaluated_group_days": evaluated,
        "insufficient_history_group_days": insufficient_history,
        "sources": sorted(df["source"].unique().tolist()),
        "currencies": sorted(df["currency"].unique().tolist()),
        "configuration": {
            "lookback_days": lookback_days,
            "min_baseline_days": min_baseline_days,
            "ratio_threshold": ratio_threshold,
            "min_cost": min_cost,
            "min_increase": min_increase,
        },
        "anomaly_report": str(anomalies_path),
    }

    # No billing totals or individual billing rows are written to the
    # console. The detailed report remains a local output file.
    (output_dir / "anomaly_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Detect unusual daily Azure costs."
    )
    parser.add_argument("--input", required=True, help="Normalized cost CSV")
    parser.add_argument("--output-dir", default="reports/anomalies")
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--min-baseline-days", type=int, default=3)
    parser.add_argument("--ratio-threshold", type=float, default=2.0)
    parser.add_argument("--min-cost", type=float, default=5.0)
    parser.add_argument("--min-increase", type=float, default=5.0)
    args = parser.parse_args()

    try:
        summary = run_detection(
            input_path=args.input,
            output_dir=args.output_dir,
            lookback_days=args.lookback_days,
            min_baseline_days=args.min_baseline_days,
            ratio_threshold=args.ratio_threshold,
            min_cost=args.min_cost,
            min_increase=args.min_increase,
        )
        print(json.dumps(summary, indent=2))
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        parser.exit(1, f"Anomaly detection failed: {exc}\n")


if __name__ == "__main__":
    main()
