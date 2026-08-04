# PR #16 Multi-Agent Review

## Scope

Review of `origin/main...feature/query-interface`, focused on concision, modularity, documentation fidelity, and tests. This is a long-term query boundary, so reviewers applied a merge-blocking standard to protocol and scalability defects.

## Reviewers

- Claude Opus 4.7: architecture, deployment, and protocol review
- Gemini 3.1 Pro: FastAPI/MCP integration and lifecycle review
- Kimi K2.7 Code: modularity and test adequacy review
- GPT 5.6 Sol: synthesis and independent reproduction

## Consensus

### Strengths

- REST and MCP adapters are small and easy to follow.
- The shared Pydantic response models avoid exposing database records directly.
- The root FastAPI lifespan correctly starts the mounted MCP session manager.
- REST tests cover exact-match filtering, OpenAPI registration, empty results, and the maximum page-size constraint.
- The approved design and README were updated in the same change rather than leaving the new interfaces undocumented.
- CI and `uv run poe check` passed with 71 tests at review time.

### Merge recommendation

**Block until the remaining query-path findings below are fixed.** The deployment-host blocker was remediated after review with configurable host/origin allowlists and a transport regression test.

## Prioritized findings

### 1. Resolved: the documented MCP endpoint rejected configured service hosts

`FastMCP` uses default DNS-rebinding protection, which only allows localhost host headers. The original README advertised a private-network IP endpoint, but that request returned `421 Invalid Host header`. The same problem applies to any non-local hostname or IP unless it is explicitly allowed.

- `src/local_vllm_dashboard/query/mcp.py:8-15`
- `README.md:52-61`
- Missing transport test: `tests/query/test_query_interface.py:86-110`

This was independently reproduced with `Host: 10.0.0.5:8010`. The follow-up configures allowed hosts and origins explicitly, generalizes the deployment documentation, and verifies accepted and rejected transport headers. The suite now passes with 72 tests.

### 2. High: pagination occurs after loading all dashboard data and artifact bytes

`QueryService.configurations()` calls `DashboardRepository.load()`, converts every matching result, then slices in Python. The dashboard loader eager-loads every bundle's artifacts, dependency revisions, observations, and metrics. Page size therefore does not bound database work or memory usage.

- `src/local_vllm_dashboard/query/service.py:17-43`
- `src/local_vllm_dashboard/dashboard/repository.py:152-169`
- `src/local_vllm_dashboard/db/models.py:57-68`

The filter-options endpoint repeats the same full dashboard load at `src/local_vllm_dashboard/query/service.py:45-56`.

### 3. High: implementation contradicts the documented module boundary

The design says `query-service` may depend on the result store/database and must not depend on dashboard presentation. The implementation imports both `DashboardFilters` and `DashboardRepository`.

- Declared boundary: `docs/DESIGN.md:69-81`
- Actual dependency: `src/local_vllm_dashboard/query/service.py:3-4`

The shared query layer should own a database-backed read repository or consume a presentation-neutral result-store query interface.

### 4. High: configuration pagination lacks a stable unique identity and ordering

A bundle can contain multiple observations, but each API item exposes only `bundle_id`, not `observation_id`. Bundles are ordered by `accepted_at`, while observations within a bundle have no explicit order. Offset pages can shift or duplicate when timestamps tie or observations change, and clients cannot uniquely identify one configuration.

- `src/local_vllm_dashboard/query/models.py:19-36`
- `src/local_vllm_dashboard/dashboard/repository.py:154-169`

### 5. Medium: REST and MCP validation semantics diverge

REST rejects invalid token counts, concurrency, limits, and offsets. MCP accepts invalid filters and silently clamps pagination. The two adapters therefore do not expose the same query semantics despite sharing a service.

- REST constraints: `src/local_vllm_dashboard/query/api.py:18-29`
- Unconstrained shared model: `src/local_vllm_dashboard/query/models.py:39-46`
- MCP clamping: `src/local_vllm_dashboard/query/mcp.py:18-44`

Move constraints into shared request models and return explicit MCP errors for invalid inputs.

### 6. Medium: tests do not prove the main deployment claim

The MCP test creates a new `FastMCP` object and calls tools directly. It bypasses `/mcp/`, transport security, the mounted Starlette app, root lifespan behavior, and Streamable HTTP protocol handling.

- `tests/query/test_query_interface.py:86-110`

The REST pagination test uses one result, `limit=1`, and `offset=0`; it cannot prove ordering or pagination.

- `tests/query/test_query_interface.py:39-64`

Missing coverage includes multiple bundles/observations, nonzero offset, stable ordering, MCP HTTP initialization/tool calls, deployed host configuration, invalid MCP inputs, and an empty database.

### 7. Medium: design documentation remains internally inconsistent

Phase 2 still says the dashboard is provided “without a separate query API,” while Phase 3 now adds one. That historical statement may be acceptable if explicitly marked as Phase 2 scope, but deployment topology and testing strategy still omit the new REST and MCP interfaces.

- Phase wording: `docs/DESIGN.md:317-323`
- Deployment omissions: `docs/DESIGN.md:277-287`
- Testing omissions: `docs/DESIGN.md:295-305`

README endpoint documentation was concise, but inaccurate because the advertised non-local MCP endpoint was rejected.

## Concision assessment

The source layout is concise: models, service, REST adapter, and MCP adapter are separated into small files. However, filter parameters and conversion logic are repeated across `models.py`, `api.py`, `mcp.py`, and `service.py`. This is manageable with seven filters but likely to drift as the contract grows. The large lockfile change is expected from adding the MCP SDK and is not hand-written bloat.

## Modularity assessment

Adapter separation is good, but the central dependency points in the wrong direction. The query service is modular at the file level yet coupled to dashboard presentation at the architecture level. Moving query persistence into a dedicated read repository would improve both modularity and database-level pagination.

## Documentation assessment

The architecture diagram, module table, delivery phase, README, and deployment topology were updated. The follow-up also documents transport host configuration and read-access assumptions. The testing strategy and protocol error semantics remain incomplete.

## Test assessment

There are useful REST and direct-tool tests, and the follow-up verifies MCP transport host/origin enforcement through the mounted endpoint. There is still no full MCP initialize/tool-call exchange over HTTP and no meaningful pagination test.

## Remediation options

| Option | Cost | Outcome and tradeoff |
| --- | --- | --- |
| Configure MCP allowed hosts and origins and add an HTTP transport test | Small | Fixes the immediate deployment blocker while retaining DNS-rebinding protection. |
| Add shared constrained request models for REST and MCP | Small | Removes semantic drift; MCP clients receive errors instead of silently clamped values. |
| Add `observation_id` and deterministic ordering | Small to medium | Makes configurations addressable and pagination repeatable; changes the public response schema before release. |
| Add a dedicated query repository with SQL filtering/count/pagination | Medium | Fixes scalability and the design-boundary violation; requires database-specific JSON filtering or normalized query columns. |
| Keep the dashboard projection temporarily but document a bounded prototype | Small | Fastest path, but preserves unbounded work and should not be described as stable pagination. |
| Expand design deployment/testing sections and add multi-record fixtures | Small | Aligns documentation and tests with the implemented architecture. |

## Reviewer disagreement

Kimi rated the change “approve with minor corrections,” emphasizing the clean adapter structure. Claude and Gemini recommended blocking because pagination is not database-backed and MCP transport is untested. Independent reproduction of the non-local-host `421` resolves the principal disagreement in favor of blocking the original PR revision.
