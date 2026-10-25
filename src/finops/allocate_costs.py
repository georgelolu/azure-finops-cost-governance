"""Validate and report FinOps costs without mixing currencies."""

from pathlib import Path
import argparse
import math

import pandas as pd


REQUIRED_COLUMNS = [
    "date", "project", "environment", "team",
    "service", "cost", "source",
]

ALLOCATION_FIELDS = ["project", "environment", "team", "service"]


def load_costs(path: str | Path) -> pd.DataFrame:
    """Load cost records, preserving optional Azure metadata."""
    df = pd.read_csv(path)

    missing = sorted(set(REQUIRED_COLUMNS) - set(df.columns))
    if missing:
        raise ValueError(
            f"Missing required columns: {', '.join(missing)}"
        )

    # Keep optional columns such as Azure IDs, charge type, and cost fields.
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["cost"] = pd.to_numeric(df["cost"], errors="coerce")

    if df["date"].isna().any():
        raise ValueError("Invalid or missing date values found.")

    if df["cost"].isna().any():
        raise ValueError("Invalid or missing cost values found.")

    if not df["cost"].map(math.isfinite).all():
        raise ValueError("Non-finite cost values found.")

    # Negative costs are valid: Azure exports may contain credits
    # and adjustments. Preserve their signs for reconciliation.
    if "currency" not in df.columns:
        df["currency"] = "UNKNOWN"

    df["currency"] = (
        df["currency"].fillna("").astype(str).str.strip().str.upper()
    )
    df.loc[df["currency"] == "", "currency"] = "UNKNOWN"

    for field in ALLOCATION_FIELDS:
        df[field] = df[field].fillna("").astype(str).str.strip()
        df[field] = df[field].replace("", "unallocated")

    df["environment"] = df["environment"].replace(
        {"unallocated": "unknown"}
    )

    df["source"] = df["source"].fillna("unknown").astype(str).str.strip()
    df.loc[df["source"] == "", "source"] = "unknown"

    if "cost_type" not in df.columns:
        df["cost_type"] = df["source"].map(
            lambda source: (
                "simulated" if source == "simulated"
                else "actual" if source == "azure_cost_export_actual"
                else "unknown"
            )
        )
    else:
        df["cost_type"] = (
            df["cost_type"].fillna("unknown").astype(str).str.strip()
        )
        df.loc[df["cost_type"] == "", "cost_type"] = "unknown"

    if "charge_type" not in df.columns:
        df["charge_type"] = ""
    else:
        df["charge_type"] = df["charge_type"].fillna("").astype(str)

    return df


def unallocated_mask(df: pd.DataFrame) -> pd.Series:
    """Identify records missing one or more allocation dimensions."""
    mask = df[ALLOCATION_FIELDS].eq("unallocated").any(axis=1)
    mask |= df["environment"].eq("unknown")
    mask |= df["service"].eq("unknown")
    return mask


def build_reports(df: pd.DataFrame, output_dir: str | Path) -> dict:
    """Write reports with currency-separated financial totals."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    # Currency is part of every financial aggregation key.
    allocation_reports = {
        "cost_by_project.csv": ["project", "currency"],
        "cost_by_environment.csv": ["environment", "currency"],
        "cost_by_team.csv": ["team", "currency"],
        "cost_by_service.csv": ["service", "currency"],
    }

    for filename, dimensions in allocation_reports.items():
        report = (
            df.groupby(dimensions, dropna=False, as_index=False)["cost"]
            .sum()
            .sort_values(["currency", "cost"], ascending=[True, False])
        )
        report["cost"] = report["cost"].round(2)
        report.to_csv(output / filename, index=False)

    daily = (
        df.groupby(["date", "currency"], as_index=False)["cost"]
        .sum()
        .sort_values(["date", "currency"])
    )
    daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")
    daily["cost"] = daily["cost"].round(2)
    daily.to_csv(output / "daily_costs.csv", index=False)

    mask = unallocated_mask(df)
    unallocated = df.loc[mask].copy()
    unallocated["date"] = unallocated["date"].dt.strftime("%Y-%m-%d")
    unallocated.to_csv(output / "unallocated_costs.csv", index=False)

    summary_rows = []
    for currency, group in df.groupby("currency", dropna=False, sort=True):
        group_mask = mask.loc[group.index]
        missing = group.loc[group_mask]

        record_count = len(group)
        unallocated_count = len(missing)
        total_signed = float(group["cost"].sum())
        unallocated_signed = float(missing["cost"].sum())
        absolute_total = float(group["cost"].abs().sum())
        unallocated_absolute = float(missing["cost"].abs().sum())

        # Absolute amounts prevent credits from hiding allocation gaps.
        record_percentage = (
            unallocated_count / record_count * 100
            if record_count else 0.0
        )
        cost_percentage = (
            unallocated_absolute / absolute_total * 100
            if absolute_total else 0.0
        )

        # Report coverage independently for each allocation dimension.
        # Use absolute costs so credits cannot inflate coverage percentages.
        coverage_metrics = {}
        dimensions = {
            "project": ("project", {"", "unknown", "unallocated"}),
            "environment": ("environment", {"", "unknown", "unallocated"}),
            "team": ("team", {"", "unknown", "unallocated"}),
            "service": ("service", {"", "unknown", "unallocated"}),
        }

        for prefix, (field, missing_values) in dimensions.items():
            values = (
                group[field]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.lower()
            )
            covered = ~values.isin(missing_values)
            covered_count = int(covered.sum())
            covered_absolute_cost = float(
                group.loc[covered, "cost"].abs().sum()
            )

            coverage_metrics[f"{prefix}_covered_record_count"] = covered_count
            coverage_metrics[f"{prefix}_covered_record_percentage"] = round(
                covered_count / record_count * 100 if record_count else 0.0,
                2,
            )
            coverage_metrics[f"{prefix}_covered_absolute_cost"] = round(
                covered_absolute_cost, 2
            )
            coverage_metrics[f"{prefix}_covered_cost_percentage"] = round(
                covered_absolute_cost / absolute_total * 100
                if absolute_total else 0.0,
                2,
            )

        summary_rows.append({
            "currency": currency,
            "record_count": record_count,
            "total_cost": round(total_signed, 2),
            "absolute_cost_amount": round(absolute_total, 2),
            "unallocated_record_count": unallocated_count,
            "unallocated_record_percentage": round(record_percentage, 2),
            "unallocated_cost": round(unallocated_signed, 2),
            "unallocated_absolute_cost": round(unallocated_absolute, 2),
            "unallocated_cost_percentage": round(cost_percentage, 2),
            "allocated_cost_percentage": round(100 - cost_percentage, 2),
            **coverage_metrics,
            "sources": ";".join(sorted(group["source"].unique())),
        })

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(output / "summary.csv", index=False)

    # Preserve the previous return shape for single-currency callers.
    # For mixed currencies, never return a misleading combined total.
    result = {
        "record_count": len(df),
        "currency_count": int(df["currency"].nunique()),
        "total_cost": None,
        "unallocated_cost": None,
        "unallocated_percentage": None,
        "total_cost_by_currency": {},
        "output_dir": str(output),
    }

    for row in summary_rows:
        currency = row["currency"]
        result["total_cost_by_currency"][currency] = row["total_cost"]

    if len(summary_rows) == 1:
        row = summary_rows[0]
        result["total_cost"] = row["total_cost"]
        result["unallocated_cost"] = row["unallocated_cost"]
        result["unallocated_percentage"] = row[
            "unallocated_cost_percentage"
        ]

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and allocate FinOps cost records."
    )
    parser.add_argument(
        "--input", default="data/sample/costs.csv",
        help="Input CSV path",
    )
    parser.add_argument(
        "--output", default="data/processed",
        help="Output directory",
    )
    args = parser.parse_args()

    df = load_costs(args.input)
    summary = build_reports(df, args.output)

    print("FinOps cost processing completed.")
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
