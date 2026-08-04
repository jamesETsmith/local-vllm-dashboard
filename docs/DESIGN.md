# Benchmark Results Platform Design

**Status:** Approved

## 1. Purpose

This project is a benchmark results platform for runs produced by [vllm-project/perf-eval](https://github.com/vllm-project/perf-eval). It standardizes performance, accuracy, and function-calling evaluation results on the benchmark host, stores the transformed observations and selected immutable source artifacts, and presents them in a dashboard.

The platform is deliberately not a benchmark runner. `perf-eval` remains responsible for selecting workloads, provisioning and serving vLLM, executing benchmarks, and producing artifacts. This platform begins when a completed run's artifacts are available.

## 2. Goals

1. Accept standardized benchmark results over a network without granting clients database access.
2. Separate source-specific extraction, canonicalization, transport, persistence, and presentation into independently replaceable modules.
3. Preserve transformed observations and selected original workload/result files so displayed values can be interpreted and reproduced.
4. Store a stable, versioned canonical result representation independent of `perf-eval`'s internal file paths, field names, and endpoint behavior.
5. Support local individual workflows first, then shared team and CI workflows without changing the client-to-server contract.
6. Facilitate clear comparisons across workloads, vLLM versions, and benchmark settings.
7. Make retries safe and avoid duplicate logical runs or artifacts.

## 3. Non-goals

1. Reimplement `perf-eval`, vLLM, lm-evaluation-harness, BFCL, Buildkite, or GPU orchestration.
2. Require the dashboard, database, or full server application on benchmark hosts.
3. Transfer large sample-level outputs, logs, model data, or arbitrary files from the benchmark host in the initial artifact scope.
4. Rewrite historical transformed observations to match future schema revisions.
5. Store secrets, credentials, or unredacted environment variables in result metadata or artifacts.

## 4. Architecture principles

### 4.1 One-way dependency direction

Dependencies flow only from the outer source layer toward the presentation layer:

```text
PERF-EVAL MACHINE                                      DB / SERVICE MACHINE
-----------------                                      ---------------------
perf-eval artifacts
  -> source adapter
  -> canonical bundle + selected immutable artifacts
  -> publisher
  -> HTTPS ingestion API                               -> operational database
                                                       -> dashboard server
                                                       -> dashboard UI

QUERY INTERFACES
REST clients -> query API -> shared query service       -> operational database
MCP clients  -> MCP endpoint -> shared query service    -> operational database
```

The source adapter and publisher execute where `perf-eval` runs and need only local artifact access plus outbound HTTPS access to the ingestion API. The ingestion API, operational database, dashboard server, query API, MCP endpoint, and dashboard UI execute on the database/service side. The dashboard server reads PostgreSQL through the result-store interface. REST and MCP expose stable machine-readable views through a shared query service rather than exposing database tables. In the initial deployment, the dashboard, REST API, and Streamable HTTP MCP endpoint run in one FastAPI process and container behind one Uvicorn command. In a local development deployment, these roles may share one host while retaining the same interfaces and dependency direction.

A downstream layer must never parse a `perf-eval` directory or depend on a `perf-eval` Python or shell module. A source adapter must never connect directly to the production database. The UI must never parse artifacts or calculate authoritative benchmark metrics.

### 4.2 Versioned contracts at every boundary

Each boundary is a serialized, versioned contract with documented compatibility rules. An implementation can evolve internally provided it continues to honor its input and output contract. Contract versions are explicit fields, not inferred from package versions.

### 4.3 Immutable facts, replaceable projections

The service stores submitted canonical bundles, standardized observations, and selected original artifact bytes as immutable facts. Dashboard-specific query rows are replaceable projections derived from those facts. If projection logic changes, it is recomputed rather than mutating the recorded observation or artifact.

### 4.4 No shared database access from clients

Only server-side services connect to the database. The initial deployment assumes network-level access control and uses one shared bearer token for ingestion. The dashboard, REST query API, and MCP endpoint remain readable without application-layer authentication. Deployments may use a private network, an HTTPS reverse proxy, or an external authentication layer to restrict readers. The ingestion API centralizes write authentication, validation, schema management, idempotency, and backup policy while keeping database credentials off developer laptops and CI workers.

## 5. Modules and ownership

| Module | Owns | May depend on | Must not depend on |
| --- | --- | --- | --- |
| `source-adapter-perf-eval` | Discovering and reading known `perf-eval` output files; producing a canonical bundle | `perf-eval` artifacts, canonical contract | publisher internals, API implementation, database, UI |
| `contracts` | Canonical bundle schema, API schema, metric vocabulary, schema compatibility fixtures | schema validation library only | adapters, storage engine, UI |
| `publisher` | Validating, spooling, retrying, and sending one canonical bundle plus selected immutable attachments | contracts, HTTP client, local filesystem | artifact parsers, server database, UI |
| `ingestion-api` | Contract validation, attachment digest/size validation, idempotency, and durable acceptance | contracts, database interface | `perf-eval` parser, dashboard logic, UI |
| `result-store` | Transactional records, normalized canonical observations, and immutable selected artifact bytes | database engine, contracts | source parsing, UI |
| `dashboard` | Server-rendered human views, filtering, and visualization | result store, database interface | `perf-eval` formats, ingestion write paths |
| `query-service` | Stable read models, filtering, pagination, and query semantics shared by machine interfaces | result store, database interface | `perf-eval` formats, ingestion write paths, dashboard presentation |
| `query-api` | Versioned REST resources and OpenAPI documentation | query service | database tables, ingestion write paths, dashboard presentation |
| `mcp-server` | Streamable HTTP tools for machine-readable discovery and queries | query service | database tables, ingestion write paths, dashboard presentation |

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

A canonical bundle is the sole semantic write payload accepted by the publisher and ingestion API. It represents one completed attempt to execute one benchmark workload. It contains standardized observations, provenance, and attachment declarations with no database-specific identifiers. Selected original artifact bytes travel beside the bundle in the same request and are not interpreted as canonical fields.

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

### 7.6 Immutable source artifacts

The client attaches selected original `perf-eval` files unchanged: the workload YAML and the corresponding benchmark or lm-eval result JSON. Each declaration includes a logical role, safe filename, media type, byte size, and SHA-256 digest. The ingestion server verifies the declared size and digest, stores the bytes immutably, and never parses them to produce canonical observations. The dashboard may display or download these artifacts as reproduction evidence.

Sample JSONL files, logs, model data, and arbitrary additional files are excluded initially. Attachment count, individual size, and total request size are bounded. Clients must not submit secrets or unredacted sensitive configuration.

## 8. Publishing protocol

### 8.1 Client deployment

Only the adapter/publisher distribution is installed where benchmarks run. It can be a small standalone executable, Python package, or container image. The server host installs and runs the ingestion API, worker, query API, dashboard, database driver, and storage integration. The database itself runs separately and does not install client packages.

The initial command shape is:

```text
local-vllm-dashboard publish --bundle ./result-bundle.json --endpoint http://results.internal
```

A convenience command may combine adaptation and publication:

```text
local-vllm-dashboard adapt-and-publish --recipe ./workloads/example.yaml --result ./results/bench.json --endpoint http://results.internal
```

The combined command is composition only. It preserves the explicit intermediate bundle for inspection, offline transport, and test fixtures.

### 8.2 API lifecycle

1. Client reads local `perf-eval` artifacts and transforms them into a canonical bundle.
2. Client validates the bundle, selects the workload YAML and corresponding result JSON, and calculates attachment sizes and digests.
3. Client sends one multipart `POST /v1/bundles` request containing the canonical bundle and selected unchanged attachments, with an `Idempotency-Key` header.
4. Server validates the schema, attachment roles/media types, size limits, digests, and idempotency key, then atomically persists the bundle, observations, and attachments as `accepted`.
5. Server returns the accepted bundle ID or a machine-readable validation error.

The request requires no preliminary API request, upload URL, finalization request, or server-side source parsing.

### 8.3 Retry and failure behavior

- A network retry with the same idempotency key returns the original accepted bundle rather than creating a duplicate.
- A rejected bundle is never partially persisted or projected.
- Publisher retry state is local and durable. It includes the bundle path, endpoint, idempotency key, and retry attempt metadata.
- Benchmark execution is never retried by this platform. Publishing failures are reported separately from benchmark success.

## 9. Persistence design

### 9.1 Logical stores

The operational database is PostgreSQL in the initial deployment. PostgreSQL stores submitted bundle metadata, transformed observations, selected immutable source artifacts, and dashboard query projections. This keeps the initial deployment simple; artifact storage may move behind a dedicated storage interface later without changing the client contract.

| Data | Store | Mutability |
| --- | --- | --- |
| Submitted bundle metadata and validation state | PostgreSQL | Append-oriented state transitions |
| Canonical observations and metric values | PostgreSQL | Immutable after acceptance |
| Selected source artifact metadata and bytes | PostgreSQL | Immutable after acceptance |
| Dashboard query rows and aggregates | PostgreSQL | Rebuildable projections |

### 9.2 Core relational entities

- `bundle`: submission metadata, schema version, idempotency key, state, provenance, timestamps, and source identity.
- `source_artifact`: logical role, safe filename, media type, byte size, digest, and immutable bytes for a selected original file.
- `observation`: immutable canonical measurement with kind, configuration JSON, subject JSON, and source provenance.
- `metric_value`: typed, unit-bearing metric values associated with an observation.
- `projection_revision`: tracks the code/schema revision used to derive query rows.

The exact physical schema may evolve, but it must preserve this ownership model and migration path.

### 9.3 Atomicity

The single ingestion request creates the accepted bundle, source artifacts, observations, and metric values in one database transaction. This prevents the dashboard from seeing a bundle without its declared reproduction evidence or seeing partially persisted observations.

## 10. Standardization and normalization rules

### 10.1 Adapter responsibilities

The `perf-eval` adapter maps known source fields to canonical values. It must:

1. Record source file paths only as informational metadata, never as stable IDs.
2. Convert units explicitly and declare selected source files with digest, size, media type, and role.
3. Capture the exact adapter version and source format assumptions.
4. Fail clearly when required metadata is absent rather than silently guessing.
5. Keep source-specific fields in namespaced extension data and attach the unchanged selected originals separately.

For example, a raw `mean_ttft_ms` becomes `mean_ttft` with unit `s`; the original field remains in the attached benchmark JSON. Throughput is normalized per accelerator when the relevant denominator is explicitly known.

### 10.2 Server responsibilities

The ingestion server validates the canonical schema, allowed units and metric names, idempotency key, request size, and attachment integrity, then stores transformed facts and immutable selected originals. It does not parse or reinterpret attached `perf-eval` files and does not apply performance-dashboard-specific transformations.

### 10.3 Dashboard derivation responsibilities

The dashboard server derives display-only values from canonical facts while handling a request. Examples include normalized display units, task score summaries, and table groupings. These calculations are presentation concerns and do not mutate stored observations. A projection worker is deferred until data volume or repeated calculations demonstrate that one is needed.

## 11. Dashboard

Phase 2 provides a simple server-rendered dashboard that reads PostgreSQL directly through the result-store interface. It does not require a separate frontend application or projection worker.

Initial views:

1. **Performance:** per-GPU throughput and latency tables with hardware, model, token-length, and concurrency filters.
2. **Accuracy:** task scores with model, task, and few-shot settings.
3. **Raw Data Table:** run provenance, canonical observation details, and selected original workload/result files needed to understand and reproduce displayed results.

The ATOM benchmark dashboard is the interaction reference: a small number of tabs, centralized filter state, native tables, and charts only where they make comparisons clearer. The implementation remains server-rendered and progressively enhanced so Phase 2 does not require a separate browser application architecture. A Help tab renders the canonical usage guide for people and agents. The same guide is exposed as `/llms.txt`; REST endpoint contracts remain generated from FastAPI/Pydantic through `/docs` and `/openapi.json`, while MCP tool instructions remain generated from registered tool definitions.

## 12. Deployment topology

### 12.1 Development and single-user deployment

A Docker Compose environment runs PostgreSQL and one FastAPI process containing the ingestion API, dashboard, REST query API, and Streamable HTTP MCP endpoint. The publisher runs on the local benchmark host and targets the local or remote ingestion API.

### 12.2 Shared deployment

PostgreSQL supports the FastAPI service and remains a private network service. Benchmark workers and CI agents require network access to the ingestion endpoint. Human and machine readers access the dashboard, REST API, or MCP endpoint through a private network or HTTPS reverse proxy. MCP DNS-rebinding protection uses an explicit allowlist of externally visible hostnames or IP addresses and origins.

The ingestion API is the only write boundary. The dashboard, REST API, and MCP endpoint are read-only and rely on deployment-level access control until application-layer reader authentication is introduced.

## 13. Observability and operations

The server emits structured logs, request IDs, and bundle IDs. Metrics cover accepted/rejected bundles, validation error categories, request size, ingestion latency, dashboard render latency, and database growth.

Operational runbooks cover database backup/restore, failed-ingestion investigation, dashboard query investigation, and schema reset procedures during early development.

## 14. Testing strategy

1. Contract fixtures: versioned canonical bundles for valid, invalid, and forward-compatibility cases.
2. Adapter golden tests: representative `perf-eval` fixture directories produce exact canonical bundles and raw-artifact provenance.
3. Publisher tests: multipart submission, single-request retry, idempotency, request failure, and offline spool behavior.
4. API tests: schema validation, attachment role/media/digest validation, duplicate submissions, size limits, and atomic persistence.
5. Dashboard repository tests: filters correctly expose workloads, versions, and benchmark settings.
6. Dashboard rendering tests: stored performance and accuracy observations appear in the expected views.
7. End-to-end test: adapter fixture to publisher to local server to rendered dashboard.
8. Query-interface tests: REST filtering and pagination, generated OpenAPI paths, MCP tools and transport security, and shared Help/agent documentation rendering.

No dashboard test should require a live `perf-eval` installation. No adapter test should require a database or dashboard.

## 15. Delivery phases

### Phase 0: Contract foundation

Create the contracts package, canonical v1 JSON schema, metric vocabulary, fixtures, and compatibility policy. No network service or dashboard is built before these are reviewed.

### Phase 1: Single-user ingestion vertical slice

Build the `perf-eval` adapter, local publisher, single-request ingestion API, and PostgreSQL persistence. Support performance raw JSON and lm-eval result JSON. Transform inputs and retain raw artifacts on the benchmark host; submit only transformed data and raw-artifact provenance. Provide Compose deployment and end-to-end fixtures.

### Phase 2: Simple dashboard

Add a server-rendered dashboard that reads PostgreSQL through the result-store interface. Provide filtered performance, accuracy, and run-data views without a separate query API, frontend application, or projection worker.

### Phase 3: Query interfaces

Add a read-only, versioned REST API for configuration discovery, filtering, pagination, and metric retrieval. Define stable API read models guided by canonical domain concepts and existing dashboard projections rather than exposing database tables. Add a Streamable HTTP MCP endpoint as a thin adapter over the same query service. Run the dashboard, REST API, and MCP endpoint in one FastAPI process and container behind one Uvicorn command.

### Shelved: Additional input coverage

Richer BFCL handling, additional `perf-eval` artifact formats, and custom dimensions remain deferred until concrete user needs and representative fixtures are available.

## 16. Resolved implementation decisions

1. **Initial scope:** Begin with Phase 0 and Phase 1 only, supporting performance and lm-eval result artifacts first.
2. **Infrastructure:** Use PostgreSQL and Docker Compose for local development.
3. **Transport:** Send one bearer-token-authenticated multipart `POST /v1/bundles` request over the deployment network containing transformed data and selected unchanged source attachments.
4. **Boundary:** Install the adapter/publisher on benchmark clients; run the full service stack only on the server side; clients have no database access; servers do not parse attached source files.
5. **Storage policy:** Submitted canonical bundles, observations, and selected original workload/result files are immutable; dashboard projections are rebuildable; large or arbitrary artifacts remain on the benchmark host.
6. **Schema policy:** Start with a simple canonical v1 schema, then iteratively extend it as concrete inputs and dashboard needs emerge. Schema changes remain explicit, versioned, and covered by fixtures; a new major version is reserved for incompatible changes.

## 17. Approval status

This document is the approved architecture source of truth. Do not modify it without the user's explicit permission.
