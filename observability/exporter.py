import csv
import math
import os
import time
from collections import defaultdict
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA_FILE = Path(
    os.environ.get("FINOPS_DATA_FILE", "/app/demo/costs.csv")
)
PORT = int(os.environ.get("PORT", "9108"))
BUDGET_USD = 10.0

REQUIRED = {
    "date", "project", "environment", "team",
    "service", "cost", "currency", "source",
}


def load_metrics():
    with DATA_FILE.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("Synthetic CSV is missing required columns")

        rows = list(reader)

    if not rows:
        raise ValueError("Synthetic CSV contains no rows")

    daily = defaultdict(float)
    projects = defaultdict(float)
    services = defaultdict(float)
    environments = defaultdict(float)
    unallocated = 0.0
    history = defaultdict(dict)
    sources = set()
    currencies = set()

    for row in rows:
        if row["source"] != "simulated":
            raise ValueError("Demo exporter accepts simulated data only")
        if row["currency"].upper() != "USD":
            raise ValueError("Demo exporter accepts USD data only")

        date.fromisoformat(row["date"])
        cost = float(row["cost"])
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("Demo costs must be finite and non-negative")

        project = row["project"]
        service = row["service"]
        environment = row["environment"]
        day = row["date"]

        daily[day] += cost
        projects[project] += cost
        services[service] += cost
        environments[environment] += cost
        history[(project, service)][day] = (
            history[(project, service)].get(day, 0.0) + cost
        )
        if any(
            row[field].strip().lower() in {"", "unknown", "unallocated"}
            for field in ("project", "environment", "team", "service")
        ):
            unallocated += cost

        sources.add(row["source"])
        currencies.add(row["currency"].upper())

    lines = [
        "# HELP finops_demo_total_cost_usd Total synthetic sample-window cost in USD.",
        "# TYPE finops_demo_total_cost_usd gauge",
        f"finops_demo_total_cost_usd {sum(daily.values())}",
        "# HELP finops_demo_monthly_budget_usd Configured demo budget reference in USD.",
        "# TYPE finops_demo_monthly_budget_usd gauge",
        f"finops_demo_monthly_budget_usd {BUDGET_USD}",
        "# HELP finops_demo_budget_utilization_ratio Sample-window spend divided by budget reference.",
        "# TYPE finops_demo_budget_utilization_ratio gauge",
        f"finops_demo_budget_utilization_ratio {sum(daily.values()) / BUDGET_USD}",
        "# HELP finops_demo_unallocated_cost_usd Synthetic costs with any unallocated dimension.",
        "# TYPE finops_demo_unallocated_cost_usd gauge",
        f"finops_demo_unallocated_cost_usd {unallocated}",
        "# HELP finops_demo_input_records Number of synthetic input records.",
        "# TYPE finops_demo_input_records gauge",
        f"finops_demo_input_records {len(rows)}",
        "# HELP finops_demo_source_is_simulated Confirms the demo source is synthetic.",
        "# TYPE finops_demo_source_is_simulated gauge",
        "finops_demo_source_is_simulated 1",
        "# HELP finops_demo_daily_cost_usd Daily synthetic cost in USD.",
        "# TYPE finops_demo_daily_cost_usd gauge",
    ]

    for day, value in sorted(daily.items()):
        lines.append(f'finops_demo_daily_cost_usd{{date="{day}"}} {value}')

    for metric, label, values, help_text in [
        ("finops_demo_project_cost_usd", "project", projects, "Synthetic cost by project in USD."),
        ("finops_demo_service_cost_usd", "service", services, "Synthetic cost by service in USD."),
        ("finops_demo_environment_cost_usd", "environment", environments, "Synthetic cost by environment in USD."),
    ]:
        lines.extend([f"# HELP {metric} {help_text}", f"# TYPE {metric} gauge"])
        for name, value in sorted(values.items()):
            safe_name = name.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            lines.append(f'{metric}{{{label}="{safe_name}"}} {value}')

    anomalies = 0
    for daily_values in history.values():
        days = sorted(daily_values)
        for index in range(3, len(days)):
            previous = [daily_values[d] for d in days[max(0, index - 7):index]]
            baseline = sorted(previous)[len(previous) // 2]
            observed = daily_values[days[index]]
            if baseline > 0 and observed >= 2 * baseline and observed - baseline >= 1:
                anomalies += 1

    lines.extend([
        "# HELP finops_demo_cost_anomalies_total Synthetic daily cost spikes detected.",
        "# TYPE finops_demo_cost_anomalies_total gauge",
        f"finops_demo_cost_anomalies_total {anomalies}",
    ])

    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path != "/metrics":
            self.send_error(404)
            return

        try:
            body = load_metrics().encode("utf-8")
        except Exception as exc:
            print(f"Metrics generation failed: {exc}", flush=True)
            self.send_error(500, "Metrics generation failed")
            return

        self.send_response(200)
        self.send_header(
            "Content-Type", "text/plain; version=0.0.4; charset=utf-8"
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"FinOps demo exporter listening on port {PORT}", flush=True)
    server.serve_forever()
