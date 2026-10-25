# Azure Cost Management Budget Governance

## Configuration
- Scope: Azure subscription
- Budget name: azure-finops-monthly-10usd
- Monthly budget: USD 10
- Budget period: Monthly
- Actual-cost notification thresholds: 50%, 80%, 100%
- Notification recipient: Configured in Azure; intentionally not published here.
- Status: Configuration verified using Azure Cost Management REST API.

## Alert thresholds
| Threshold | Spend level |
|---|---:|
| 50% | USD 5 |
| 80% | USD 8 |
| 100% | USD 10 |

## Operational notes
- Azure budget alerts are notifications, not spending caps.
- Cost data may be delayed.
- Configuration verification does not prove email delivery.
- Do not commit raw billing exports, credentials, or account-specific secrets.
