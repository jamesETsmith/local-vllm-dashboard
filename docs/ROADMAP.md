# Project Roadmap

This roadmap tracks implementation progress against the architecture in [DESIGN.md](DESIGN.md). The approved design remains the source of truth for system boundaries and scope.

## Completed

### Contract and ingestion foundation

- Define the canonical v1 bundle, metric vocabulary, fixtures, and compatibility rules.
- Adapt performance and lm-eval artifacts into canonical observations.
- Publish authenticated multipart bundles with idempotent persistence.
- Retain selected workload and result artifacts with validated metadata and content.
- Support directory ingestion, browser upload, and benchmark-host result packaging.
- Capture vLLM and dependency revisions while the benchmark runtime is available.
- Store dependency revisions as queryable run metadata.

### Dashboard

- Provide server-rendered performance, accuracy, raw-data, and run-detail views.
- Filter dashboard results without mixing state between tabs.
- Compare each model in a separate concurrency chart.
- Switch performance charts between total token throughput, output token throughput, TTFT, and TPOT.
- Preserve per-GPU throughput normalization and AMD/NVIDIA color conventions.
- Show metric names and units on chart axes and configuration details on point hover.
- Export the filtered raw-data selection as CSV.
- Link chart points and raw-data rows to complete run provenance.

### Reliability

- Migrate legacy artifact tables that predate stored media types and content.
- Backfill dependency revisions from existing canonical bundle payloads.
- Isolate browser-upload failures by rolling back each failed ingestion item.
- Cover contracts, adapters, ingestion, persistence, uploads, dashboard projections, and rendering with automated tests.

## Next

### Additional input coverage

- Expand BFCL-specific result handling and presentation.
- Add concrete adapters for additional perf-eval artifact formats as fixtures become available.
- Promote comparison-relevant custom dimensions through explicit contract revisions.
- Extend raw-data filters and CSV export together when new dimensions are exposed.

### Dashboard validation and maintainability

- Add browser-level tests for metric switching, hover details, keyboard interaction, and run navigation.
- Share raw-data column metadata between the HTML table and CSV export.
- Add regression fixtures for multi-model, mixed-vendor, and incomplete-metric datasets.
- Continue accessibility and responsive-layout validation for dense benchmark collections.

### Operations

- Document backup, restore, and upgrade procedures for persistent deployments.
- Add deployment health checks and production-oriented service configuration.
- Define retention and size policies for stored source artifacts.

## Later

### Machine-readable query interface

- Define stable read models for run discovery, filtering, and metric retrieval.
- Add an MCP server over the result-store interface without exposing database access.
- Preserve the dashboard and ingestion boundaries established in the approved design.
