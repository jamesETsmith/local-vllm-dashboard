# Development

The architecture and scope are defined in [DESIGN.md](DESIGN.md).

Install dependencies once:

```text
uv sync --all-groups
```

Run project tasks through the unified interface:

```text
uv run poe check
uv run poe test
uv run poe format
uv run poe security
uv run poe up
uv run poe down
uv run poe reset
```

Generate and export one ingestion token before starting the service:

```text
export DASHBOARD_INGEST_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

`up` starts PostgreSQL, creates the current schema from scratch, and starts the ingestion service and dashboard. Open `http://localhost:8000/dashboard/` to view stored results. The dashboard remains readable without authentication; `POST /v1/bundles` requires the bearer token. During early development, schema changes are intentionally breaking; use `uv run poe reset` to remove the database volume before restarting.

Create a canonical performance bundle from `perf-eval` files:

```text
uv run benchmark-results adapt-perf --recipe workload.yaml --result bench.json --output bundle.json
```

Publish it in one request:

```text
uv run benchmark-results publish \
  --bundle bundle.json \
  --endpoint http://localhost:8000
```
