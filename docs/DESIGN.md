# Benchmark Results Platform Design

**Status:** Approved

## 1. Purpose

This project is a benchmark-results platform for runs produced by [vllm-project/perf-eval](https://github.com/vllm-project/perf-eval). It standardizes performance, accuracy, and function-calling evaluation results on the benchmark host, stores the transformed observations and their provenance, and presents them in a dashboard. Raw source artifacts remain on the benchmark host.

The platform is deliberately not a benchmark runner. `perf-eval` remains responsible for selecting workloads, provisioning and serving vLLM, executing benchmarks, and producing artifacts. This platform begins when a completed run's artifacts are available.

## 2. Goals

1. Accept standardized benchmark results over a network without granting clients database access.
2. Separate source-specific extraction, canonicalization, transport, persistence, and presentation into independently replaceable modules.
3. Preserve the transformed observations and enough provenance to reproduce or correctly interpret every displayed value, while retaining raw source artifacts on the benchmark host.
4. Store a stable, versioned canonical result representation independent of `perf-eval`'s internal file paths, field names, and endpoint behavior.
5. Support local individual workflows first, then shared team and CI workflows without changing the client-to-server contract.
6. Facilitate clear comparisons across workloads, vLLM versions, and benchmark settings.
7. Make retries safe and avoid duplicate logical runs or artifacts.

## 3. Non-goals

1. Reimplement `perf-eval`, vLLM, lm-evaluation-harness, BFCL, Buildkite, or GPU orchestration.
2. Require the dashboard, database, or full server application on benchmark hosts.
3. Transfer or centrally store raw `perf-eval` artifacts in the initial scope.
4. Rewrite historical transformed observations to match future schema revisions.
5. Store secrets, credentials, or unredacted environment variables in result metadata.

## 4. Architecture principles

### 4.1 One-way dependency direction

Dependencies flow only from the outer source layer toward the presentation layer:

```text
PERF-EVAL MACHINE                                      DB / SERVICE MACHINE
-----------------                                      ---------------------
perf-eval artifacts
  -> source adapter
  -> canonical bundle
  -> publisher
  -> HTTPS ingestion API                               -> immutable artifact storage + operational database
                                                       -> derived-query worker
                                                       -> dashboard API
                                                       -> dashboard UI
```

The source adapter and publisher execute where `perf-eval` runs and need only local artifact access plus outbound HTTPS access to the ingestion API. The ingestion API, artifact storage, operational database, projection worker, dashboard API, and dashboard UI execute on the database/service side. In a local development deployment, these roles may share one host while retaining the same interfaces and dependency direction.

A downstream layer must never parse a `perf-eval` directory or depend on a `perf-eval` Python or shell module. A source adapter must never connect directly to the production database. The UI must never parse artifacts or calculate authoritative benchmark metrics.

### 4.2 Versioned contracts at every boundary

Each boundary is a serialized, versioned contract with documented compatibility rules. An implementation can evolve internally provided it continues to honor its input and output contract. Contract versions are explicit fields, not inferred from package versions.

### 4.3 Immutable facts, replaceable projections

The service stores submitted canonical bundles and their standardized observations as immutable facts. Dashboard-specific query rows are replaceable projections derived from those facts. If projection logic changes, it is recomputed rather than mutating the recorded observation.

### 4.4 No shared database access from clients

Only server-side services connect to the database. The initial deployment is restricted to one trusted network and does not require application-layer authentication or scoped tokens. The ingestion API still centralizes validation, migrations, idempotency, and backup policy while keeping database credentials off developer laptops and CI workers.

## 5. Modules and ownership

| Module | Owns | May depend on | Must not depend on |
| --- | --- | --- | --- |
| `source-adapter-perf-eval` | Discovering and reading known `perf-eval` output files; producing a canonical bundle | `perf-eval` artifacts, canonical contract | publisher internals, API implementation, database, UI |
| `contracts` | Canonical bundle schema, API schema, metric vocabulary, schema compatibility fixtures | schema validation library only | adapters, storage engine, UI |
| `publisher` | Validating, spooling, retrying, and sending one canonical bundle request | contracts, HTTP client, local filesystem | artifact parsers, server database, UI |
| `ingestion-api` | Contract validation, idempotency, and durable acceptance | contracts, database interface | `perf-eval` parser, dashboard logic, UI |
| `result-store` | Transactional records and normalized canonical observations | database engine, contracts | source file formats, UI |
| `projection-worker` | Dashboard query rows and aggregates | result store, contracts | HTTP request lifecycle, UI |
| `query-api` | Read-only dashboard query models and filtering | projections, result store | `perf-eval`, artifact parsing, write paths |
| `dashboard` | Human-facing exploration and visualization | query API contract | database, `perf-eval` formats |

Implementations may live in one repository and deploy together initially, but package and interface boundaries remain enforced. In-process calls are allowed only behind the same contract-oriented interfaces as future network calls.

## 6. Integration with perf-eval

`perf-eval` currently produces multiple artifact families:

- `vllm bench serve` writes raw JSON via `--save-result`, conventionally `bench-<config-name>.json`.
- lm-evaluation-harness writes `results_*.json` and, when sample logging is enabled, `samples_*.jsonl` under its task output directory.
- BFCL is transformed to lm-eval-style task results by the runner.
- The current upstream ingestion scripts transform and post some result shapes directly to separate, purpose-specific hosted endpoints.

This platform does not use those upstream endpoint payloads as its internal schema. Instead, a `source-adapter-perf-eval` reads the local output directory and workload context and emits one canonical bundle. The adapter should be executable as a standalone CLI and can be invoked as a final `perf-eval` pipeline step or independently after a run.

No upstream changes are required for the first version. A later optional upstream integration may invoke the adapter automatically, but the adapter remains a separate package and does not change the server contract.

## 7. Canonical bundle contract

### 7.1 Bundle purpose

A canonical bundle is the sole write payload accepted by the publisher and ingestion API. It represents one completed attempt to execute one benchmark workload. It contains standardized observations and provenance, with no database-specific identifiers or raw artifact bytes.

### 7.2 Envelope

```json
{
  "schema_version": "v1",
  "bundle_id": "018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1a",
  "idempotency_key": "sha256:...",
  "run": {},
  "workload": {},
  "environment": {},
  "observations": [],
  "labels": {}
}
```

- `bundle_id` is a client-generated UUIDv7 identifying this submission attempt.
- `idempotency_key` is a deterministic SHA-256 digest of the semantic bundle content. Retrying the same completed run must reuse it.
- `schema_version` uses major versions such as `v1`. The server rejects unsupported major versions with a machine-readable error.
- Unknown fields are rejected in v1 except within explicitly designated extension maps. This prevents silent data loss or accidental schema drift.

### 7.3 Run provenance

The `run` object identifies when and how the benchmark was executed:

```json
{
  "started_at": "2026-07-23T14:01:02Z",
  "completed_at": "2026-07-23T14:16:48Z",
  "status": "completed",
  "runner": { "kind": "buildkite", "run_id": "...", "url": "..." },
  "source": { "kind": "perf-eval", "revision": "git-sha-if-known" },
  "vllm": { "commit": "abc123", "image": "registry/image:tag" }
}
```

The server assigns its own accepted timestamp and tenant/project identity. Client-supplied timestamps remain recorded provenance and are not trusted for access control.

### 7.4 Workload and environment

`workload` describes the declared benchmark configuration: workload name, source recipe content digest, model identifier, benchmark configuration names, task identifiers, and optional recipe reference. The raw recipe is attached as an artifact where available.

`environment` captures only allowlisted, comparison-relevant details: accelerator model, accelerator count, topology, parallelism degrees, host operating-system details, framework version, and explicit precision. Environment metadata has an extension map for source-specific nonsecret fields. Arbitrary process environments are never submitted.

### 7.5 Observations

An observation records values emitted by one measurement unit. It has a stable identity inside a bundle:

```json
{
  "observation_id": "bench:1k-in-1k-out-conc-256",
  "kind": "performance",
  "subject": { "model": "Qwen/Qwen3.5-397B-A17B-FP8" },
  "configuration": {
    "input_tokens": 1024,
    "output_tokens": 1024,
    "max_concurrency": 256,
    "dataset": "random",
    "backend": "openai"
  },
  "metrics": [
    { "name": "total_token_throughput", "value": 1234.5, "unit": "token/s", "aggregation": "run" },
    { "name": "mean_ttft", "value": 0.091, "unit": "s", "aggregation": "mean" }
  ],
  "source": { "adapter": "perf-eval", "adapter_version": "1.0.0" }
}
```

Supported v1 kinds are `performance`, `accuracy`, and `function_calling`. Metric names come from a controlled vocabulary. Original source field names and noncanonical values are retained in the artifact, not promoted into arbitrary dashboard columns.

Accuracy observations identify evaluation task, task configuration such as few-shot count, score name, score value, optional standard error, and whether the result is partial. Sample-level outputs are artifacts, not rows in the primary dashboard query model.

### 7.6 Raw artifact provenance

Raw `perf-eval` files are retained on the benchmark host and are not transmitted in v1. The bundle records source artifact metadata needed for traceability: relative path, content role, byte size, and SHA-256 digest. The source adapter may include this metadata in its namespaced source extension, but the server treats it as provenance only and does not fetch or store the file.

## 8. Publishing protocol

### 8.1 Client deployment

Only the adapter/publisher distribution is installed where benchmarks run. It can be a small standalone executable, Python package, or container image. The server host installs and runs the ingestion API, worker, query API, dashboard, database driver, and storage integration. The database itself runs separately and does not install client packages.

The initial command shape is:

```text
benchmark-results publish --bundle ./result-bundle.json --endpoint http://results.internal/v1/bundles
```

A convenience command may combine adaptation and publication:

```text
benchmark-results perf-eval publish --results-dir ./results --workload ./workloads/example.yaml
```

The combined command is composition only. It preserves the explicit intermediate bundle for inspection, offline transport, and test fixtures.

### 8.2 API lifecycle

1. Client reads and transforms local `perf-eval` artifacts into a canonical bundle, recording raw artifact provenance but retaining the files locally.
2. Client validates the canonical bundle locally.
3. Client sends the transformed bundle in one `POST /v1/bundles` request with an `Idempotency-Key` header.
4. Server validates the schema, size limit, and idempotency key, then atomically persists the bundle and observations as `accepted` and queues dashboard projections.
5. Server returns the accepted bundle ID or a machine-readable validation error. The client may query `GET /v1/bundles/{bundle_id}` for persisted state.

The request contains no raw benchmark artifact bytes and requires no preliminary API request, upload URL, or finalization request.

### 8.3 Retry and failure behavior

- A network retry with the same idempotency key returns the original accepted bundle rather than creating a duplicate.
- A rejected bundle is never partially persisted or projected.
- Publisher retry state is local and durable. It includes the bundle path, endpoint, idempotency key, and retry attempt metadata.
- Benchmark execution is never retried by this platform. Publishing failures are reported separately from benchmark success.

## 9. Persistence design

### 9.1 Logical stores

The operational database is PostgreSQL in the initial deployment. PostgreSQL stores submitted bundle metadata, transformed observations, and dashboard query projections. Raw source artifacts remain on the benchmark host and are outside the database's storage responsibility.

| Data | Store | Mutability |
| --- | --- | --- |
| Submitted bundle metadata and validation state | PostgreSQL | Append-oriented state transitions |
| Canonical observations and metric values | PostgreSQL | Immutable after acceptance |
| Raw artifact provenance metadata | PostgreSQL | Immutable after acceptance |
| Dashboard query rows and aggregates | PostgreSQL | Rebuildable projections |

### 9.2 Core relational entities

- `bundle`: submission metadata, schema version, idempotency key, state, provenance, timestamps, and source identity.
- `raw_artifact_provenance`: role, relative path, byte size, and digest for a raw file retained by the benchmark host.
- `observation`: immutable canonical measurement with kind, configuration JSON, subject JSON, and source provenance.
- `metric_value`: typed, unit-bearing metric values associated with an observation.
- `projection_revision`: tracks the code/schema revision used to derive query rows.

The exact physical schema may evolve, but it must preserve this ownership model and migration path.

### 9.3 Atomicity

The single ingestion request creates the accepted bundle, raw artifact provenance, observations, and metric values in one database transaction. A worker is notified through a transactional outbox written in the same transaction. This prevents a dashboard from seeing partially persisted results and prevents lost projection work when a process crashes.

## 10. Standardization and normalization rules

### 10.1 Adapter responsibilities

The `perf-eval` adapter maps known source fields to canonical values. It must:

1. Record source file paths only as informational metadata, never as stable IDs.
2. Convert units explicitly and record the raw file digest and role as provenance.
3. Capture the exact adapter version and source format assumptions.
4. Fail clearly when required metadata is absent rather than silently guessing.
5. Keep source-specific fields in namespaced extension data; retain the corresponding raw artifacts on the benchmark host.

For example, a raw `mean_ttft_ms` becomes `mean_ttft` with unit `s`; the original field remains in the local raw benchmark JSON and its digest is recorded with the submission. Throughput is initially stored as the benchmark-reported aggregate throughput. Per-accelerator throughput is a derived metric only when the relevant denominator is explicitly known.

### 10.2 Server responsibilities

The ingestion server validates the canonical schema, allowed units and metric names, idempotency key, and request size, then stores transformed facts. It does not fetch, verify, or reinterpret local `perf-eval` source artifacts, and it does not apply performance-dashboard-specific transformations.

### 10.3 Projection responsibilities

The worker derives user-facing values from canonical facts under a named projection revision. Examples include per-GPU throughput, normalized display units, task score summaries, and percentile displays. Every derived value records the observation and projection revision from which it came.

## 12. Dashboard and query API

The dashboard consumes only the read-only query API. It does not access PostgreSQL or object storage directly.

Initial views:

1. **Runs:** status, source and vLLM provenance, workload, environment, submission time, and ingestion validation state.
2. **Run detail:** canonical observations, metric values, raw-artifact provenance, and adapter/projection versions.
3. **Performance explorer:** filtered tables across workloads, vLLM versions, and benchmark settings.
4. **Accuracy explorer:** task scores across workloads, vLLM versions, and task settings, including partial-result markers.

Query endpoints return stable view models rather than raw relational tables. Example endpoint families are `GET /v1/runs`, `GET /v1/runs/{id}`, and `GET /v1/metrics`.

## 12. Deployment topology

### 12.1 Development and single-user deployment

A Docker Compose environment runs PostgreSQL, ingestion API, worker, query API, and dashboard. The publisher runs on the local benchmark host and targets the local or remote ingestion API.

### 12.2 Shared deployment

PostgreSQL supports stateless ingestion API, worker, query API, and dashboard instances. Background workers scale independently from HTTP services. Benchmark workers and CI agents require only network access to the ingestion endpoint.

The API is the only write boundary. PostgreSQL remains a private network service.

## 13. Observability and operations

The server emits structured logs, request IDs, and bundle IDs. Metrics cover accepted/rejected bundles, validation error categories, request size, ingestion latency, projection queue lag, projection failures, query latency, and database growth.

Operational runbooks cover database backup/restore, queued projection replay, projection rebuild by revision, failed-ingestion investigation, and schema migration rollback.

## 14. Testing strategy

1. Contract fixtures: versioned canonical bundles for valid, invalid, and forward-compatibility cases.
2. Adapter golden tests: representative `perf-eval` fixture directories produce exact canonical bundles and raw-artifact provenance.
3. Publisher tests: single-request retry, idempotency, request failure, and offline spool behavior.
4. API tests: schema validation, duplicate submissions, size limits, and atomic persistence.
5. Projection tests: deterministic dashboard query rows and aggregates.
6. Query tests: filters correctly expose workloads, versions, and benchmark settings.
7. End-to-end test: adapter fixture to publisher to local server to dashboard query.

No dashboard test should require a live `perf-eval` installation. No adapter test should require a database or dashboard.

## 15. Delivery phases

### Phase 0: Contract foundation

Create the contracts package, canonical v1 JSON schema, metric vocabulary, fixtures, and compatibility policy. No network service or dashboard is built before these are reviewed.

### Phase 1: Single-user ingestion vertical slice

Build the `perf-eval` adapter, local publisher, single-request ingestion API, PostgreSQL persistence, and one run-detail query endpoint. Support performance raw JSON and lm-eval result JSON. Transform inputs and retain raw artifacts on the benchmark host; submit only transformed data and raw-artifact provenance. Provide Compose deployment and end-to-end fixtures.

### Phase 2: Query model and dashboard

Add projection worker, run list, run detail, and filtered performance and accuracy explorers across workloads, vLLM versions, and benchmark settings.

### Phase 3: Additional input coverage

Add richer BFCL handling, additional `perf-eval` artifact formats, custom dimensions, and optional data export.

## 16. Resolved implementation decisions

1. **Initial scope:** Begin with Phase 0 and Phase 1 only, supporting performance and lm-eval result artifacts first.
2. **Infrastructure:** Use PostgreSQL and Docker Compose for local development.
3. **Transport:** Send one unauthenticated `POST /v1/bundles` request over the trusted network. The request contains transformed data only.
4. **Boundary:** Install the adapter/publisher on benchmark clients; run the full service stack only on the server side; clients have no database access.
5. **Storage policy:** Retain raw artifacts on the benchmark host. Submitted canonical bundles and observations are immutable; dashboard projections are rebuildable.
6. **Schema policy:** Start with a simple canonical v1 schema, then iteratively extend it as concrete inputs and dashboard needs emerge. Schema changes remain explicit, versioned, and covered by fixtures; a new major version is reserved for incompatible changes.

## 17. Approval status

This document is the approved architecture source of truth. Do not modify it without the user's explicit permission.
