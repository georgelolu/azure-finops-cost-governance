# FinOps Project Evidence

This directory contains screenshots demonstrating selected implementation,
testing, monitoring, and governance capabilities of the Azure FinOps project.

## Evidence Screenshots

| Screenshot | What it demonstrates |
|---|---|
| `screenshots/01-grafana-finops-dashboard.png` | Local Grafana dashboard using Prometheus and synthetic FinOps metrics. |
| `screenshots/03-azure-budget-governance.png` | Azure Cost Management budget configuration and governance thresholds. |
| `screenshots/04-pytest-results.png` | Automated Python test suite results. |

## Important Data and Security Notes

- The Grafana dashboard uses a clearly identified synthetic demonstration dataset.
- Synthetic dashboard values must not be interpreted as actual Azure expenditure.
- Budget thresholds generate notifications; they do not automatically stop spending.
- Billing information, subscription identifiers, credentials, and other sensitive
  details must be reviewed and redacted before screenshots are published.
- Screenshots demonstrate selected states at the time they were captured; they
  do not independently guarantee ongoing service health or alert delivery.

## Additional Evidence

Further evidence can be added as it becomes available, including a successful
GitHub Actions Azure export-validation run and the published architecture
documentation.
