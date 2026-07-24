# Development

The architecture and scope are defined in [DESIGN.md](DESIGN.md).

```text
uv sync --all-groups
uv run pytest
uv run pre-commit run --all-files
```

Start PostgreSQL and the one-way ingestion API:

```text
docker compose up --build
```

Create a canonical performance bundle from `perf-eval` files:

```text
uv run benchmark-results adapt-perf --recipe workload.yaml --result bench.json --output bundle.json
```

Publish it in one request:

```text
uv run benchmark-results publish --bundle bundle.json --endpoint http://localhost:8000
```
