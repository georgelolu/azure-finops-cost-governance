# Azure FinOps Cost Governance — Interview Walkthrough

## 1. Project Overview

This project demonstrates how to build a cost-governance workflow on Azure
that validates exported cost data, supports cost allocation, detects unusual
spending patterns, and provides budget notifications and operational visibility.

The goal is to help engineering teams improve cloud-cost visibility and
identify unexpected cost changes without exposing sensitive billing data.

## 2. Business Problem

Cloud spending can grow unexpectedly when resources are overprovisioned,
environments remain running unnecessarily, or teams lack visibility into
which projects and services consume resources.

This project addresses those problems through automated cost-data validation,
allocation, anomaly detection, budget alerts, and monitoring.

## 3. Architecture and Data Flow

1. Azure Cost Management generates a scheduled cost export.
2. The export is delivered to a private Azure Blob Storage container.
3. Python tooling parses, normalizes, and validates the exported records.
4. Cost allocation groups records by project, environment, service, and other
   available dimensions.
5. An anomaly detector compares daily costs against a rolling historical baseline.
6. GitHub Actions runs automated tests and validates export freshness using
   Azure authentication through Microsoft Entra ID and GitHub OIDC.
7. Prometheus and Grafana demonstrate cost metrics using a separate synthetic
   dataset for safe local visualization.

See [Architecture Documentation](architecture/architecture.md).

## 4. Key Engineering Decisions

### Identity and access

GitHub Actions uses OpenID Connect (OIDC) to obtain Azure credentials without
storing a long-lived Azure client secret in GitHub repository secrets.
The workflow identity has scoped Blob Storage read access for export validation.

### Storage security

The export container is private. Shared-key access is disabled, and access
uses Microsoft Entra ID where supported. HTTPS and TLS 1.2 are configured.

### Data validation

The validation workflow checks the export schema, record integrity, currency
consistency, and freshness. It helps detect missing, malformed, or stale data
before downstream analysis.

### Cost allocation

The allocation logic groups cost records using available dimensions and
reviewed resource-group mappings. It keeps currencies separate and preserves
negative credits rather than treating them as positive spending.

### Anomaly detection

The detector compares daily costs with a rolling median baseline and applies
configurable minimum-history, ratio, and absolute-increase thresholds.
Synthetic tests exercise cost spikes, credits, missing dates, insufficient
history, and source/currency separation.

### Budget governance

An Azure Cost Management budget is configured with 50%, 80%, and 100%
notification thresholds. Budget alerts notify stakeholders; they do not
automatically stop Azure resources or cap spending. Billing data and alert
evaluation can be delayed.

## 5. Monitoring Dashboard

The local Grafana dashboard uses Prometheus and a Python metrics exporter.
It displays synthetic cost, allocation, and anomaly metrics.

**Important:** Grafana's current demonstration data is synthetic. It is not
a live visualization of actual Azure billing records. Its $10 budget reference
is illustrative and must not be interpreted as a spending limit.

## 6. Testing and CI/CD

The Python test suite covers allocation, export validation, and anomaly
detection. At the latest documented checkpoint, 27 tests passed, and the
GitHub Actions Azure export-validation workflow completed successfully.

The workflow uses a scheduled run and supports manual execution. It validates
the latest available export against a freshness requirement and avoids logging
sensitive billing totals.

## 7. Security and Operational Limitations

- Budget alerts are notifications, not enforcement controls.
- Azure Cost Management data is not necessarily real-time.
- Local Grafana metrics are synthetic and separate from actual billing data.
- Anomaly detection depends on sufficient history and suitable thresholds.
- Cost allocation depends on data quality, tags, and mapping coverage.
- Production deployment would require alert delivery verification, operational
  runbooks, access reviews, retention decisions, and cost-aware testing.

## 8. Five-Minute Demonstration Plan

1. **Overview (30 seconds):** Explain the cloud-cost visibility problem.
2. **Architecture (60 seconds):** Walk through Cost Management, Blob Storage,
   Python processing, GitHub Actions, and the monitoring demo.
3. **Security (60 seconds):** Explain OIDC, scoped RBAC, private storage,
   and avoiding long-lived credentials.
4. **Automation (60 seconds):** Show validation tests, freshness checks,
   allocation logic, and anomaly detection.
5. **Dashboard (45 seconds):** Show the synthetic Grafana dashboard and clearly
   explain why its data is synthetic.
6. **Trade-offs (45 seconds):** Discuss alert delays, budget-notification limits,
   data quality, and future production improvements.

## 9. Interview Questions and Sample Answers

### Q1. What problem does this project solve?

It demonstrates a repeatable way to improve Azure cost visibility. It validates
exported cost data, organizes costs by useful dimensions, detects unusual daily
spending patterns, and provides budget notifications and monitoring.

### Q2. Why did you use GitHub OIDC instead of a client secret?

OIDC avoids maintaining a long-lived client secret for the workflow. GitHub
Actions requests a federated identity token, Microsoft Entra ID validates the
configured trust relationship, and Azure RBAC limits what the resulting
identity can access.

### Q3. How does the anomaly detector work?

It groups daily costs by source, currency, project, environment, and service.
It compares the observed cost against a rolling median baseline and applies
minimum-history, ratio, and absolute-increase thresholds. I test edge cases
such as credits, missing dates, and insufficient history to reduce misleading
alerts.

### Q4. Does a budget alert stop spending?

No. Azure Cost Management budget thresholds generate notifications. They are
not spending caps. Automated remediation would need a separate, carefully
controlled workflow with explicit policies and safeguards.

### Q5. How do you protect billing information?

The export container is private, access is scoped, the workflow avoids printing
sensitive billing totals, and the Grafana demo uses synthetic data. Before
publishing screenshots, I also review them for subscription identifiers,
billing figures, and other sensitive information.

### Q6. How did you test the implementation?

I used automated Python tests for data validation, allocation, and anomaly
detection, then verified the GitHub Actions workflow and checked the local
Prometheus and Grafana services. The synthetic anomaly scenario also verifies
that a controlled cost spike is detected.

### Q7. What would you improve next?

I would add verified alert delivery and runbooks, improve tag and ownership
coverage, measure cost per request, define policy-based remediation with
approval safeguards, and integrate a production dashboard through a secure,
validated data path.

## 10. Repository and Evidence

- Repository: https://github.com/georgelolu/azure-finops-cost-governance
- Evidence screenshots: ../evidence/
- Architecture: architecture/architecture.md
- Workflow: ../.github/workflows/azure-cost-export-validation.yml

## 11. Interview Accuracy

Describe completed features as implemented and tested. Describe future
remediation, live billing visualization, and any unverified alert delivery as
future work or limitations. Do not claim cost savings unless measured against
a documented baseline.
