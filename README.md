# local-vllm-dashboard

Collect standardized `perf-eval` results from benchmark machines and inspect them in a shared dashboard. See [the approved design](docs/DESIGN.md) for architecture and scope.

## Dashboard host playbook

### 1. Install

```bash
git clone https://github.com/jamesETsmith/local-vllm-dashboard.git
cd local-vllm-dashboard
uv sync --locked --all-groups
```

### 2. Create persistent configuration

Generate the ingestion token once. Reuse it across restarts and share it only with approved publishing hosts. Set the public host or IP used by clients so the MCP endpoint can reject DNS-rebinding attempts without being limited to localhost.

Generate a token, then create `.env` with an editor. For example, in Bash, Zsh, or Fish:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

```dotenv
DASHBOARD_DATABASE_URL=sqlite+pysqlite:///./dashboard.db
DASHBOARD_INGEST_TOKEN=<GENERATED_TOKEN>
DASHBOARD_PUBLIC_URL=http://<SERVICE_HOST>:8010
```

Replace `<SERVICE_HOST>` with the hostname or IP that clients use, without `http://` or a trailing slash. For example, if clients open `http://server.example:8010/dashboard/`, use `DASHBOARD_PUBLIC_URL=http://server.example:8010`. Protect the file with `chmod 600 .env` on Unix-like systems.

`DASHBOARD_PUBLIC_URL` is the client-visible origin. It automatically allows that exact host and origin for MCP DNS-rebinding protection and supplies links in Help and `/llms.txt`. For reverse proxies, multiple domains, or separate browser origins, set `DASHBOARD_MCP_ALLOWED_HOSTS` and `DASHBOARD_MCP_ALLOWED_ORIGINS` explicitly; those values override the derived defaults.

The application loads `.env` automatically. Shell-specific `source` or `export` commands are not required.

### 3. Initialize and start

```bash
uv run local-vllm-dashboard serve \
  --host <BIND_ADDRESS> \
  --port 8010
```

`serve` initializes the configured database schema before starting the dashboard. Use `127.0.0.1` for local-only access or `0.0.0.0` when clients connect through the configured public address. The equivalent one-off option is `--public-url http://<SERVICE_HOST>:8010`, which overrides `DASHBOARD_PUBLIC_URL`. For broader deployments, put the service behind an HTTPS reverse proxy. Open:

```text
<BASE_URL>/dashboard/
```

The dashboard and query interfaces are readable without application-layer authentication. Writes require the token. Restrict read access with the deployment network, reverse proxy, or an external authentication layer. Keep the `.env` file private and reuse the same token across service restarts.

The same Uvicorn process also serves machine-readable query interfaces:

```text
<BASE_URL>/api/v1/configurations
<BASE_URL>/api/v1/configuration-filters
<BASE_URL>/docs
<BASE_URL>/mcp/
```

The REST API supports exact-match filters for hardware, model, precision, token lengths, prefix-cache tokens, and concurrency, with bounded `limit` and `offset` pagination. The MCP endpoint uses Streamable HTTP and exposes the same configuration search and filter discovery through shared query models.

The Custom Comparison page lets users select performance results across models and configurations and plot their throughput or latency on one graph. The dashboard Help tab and `/llms.txt` are rendered from `docs/USING_THE_DASHBOARD.md`. Update that guide instead of duplicating user or agent instructions in templates. REST contracts are generated from code at `/docs` and `/openapi.json`; MCP tool instructions are generated from tool registrations.

## Publishing host playbook

### 1. Install

```bash
git clone https://github.com/jamesETsmith/local-vllm-dashboard.git
cd local-vllm-dashboard
uv sync --locked --all-groups
```

### 2. Configure the shared token

```bash
export DASHBOARD_INGEST_TOKEN='<TOKEN_FROM_DASHBOARD_HOST>'
```

### 3. Preview discovery

```bash
uv run local-vllm-dashboard ingest-directory \
  --workloads-dir /path/to/workloads \
  --results-dir /path/to/results
```

Review the report for matched, repeated, missing, unmatched, and invalid files.

### 4. Publish

```bash
uv run local-vllm-dashboard ingest-directory \
  --workloads-dir /path/to/workloads \
  --results-dir /path/to/results \
  --endpoint <BASE_URL>
```

The command reports accepted, duplicate, and failed submissions. If the configured local Docker image or matching perf-eval container is available, ingestion also records exact vLLM and ROCm AITER revisions when detectable.

### Package results for browser upload

Run the packager on the benchmark host while its perf-eval container or configured image is still available:

```bash
uv run local-vllm-dashboard package-results \
  --workloads-dir /path/to/workloads \
  --results-dir /path/to/results \
  --output ./dashboard-results.tar.gz
```

Use `--container <NAME_OR_ID>` when automatic container discovery is ambiguous. The archive contains matched workload and result files plus revision metadata extracted with the same vLLM and ROCm AITER detection used by direct ingestion. Upload the resulting archive through the browser. Dependency commits are stored as queryable run metadata and shown in the Raw Data Table and run detail view.

## Browser upload

Open `<BASE_URL>/dashboard/upload` or select **Upload results** on the dashboard. Enter the ingestion token, then choose either:

- a local folder containing workload YAML and result JSON files; or
- a `.tar`, `.tar.gz`, or `.tgz` archive preserving their directory structure.

The server stages only YAML and JSON files, rejects unsafe archive paths, links, oversized files, and excessive uploads, then shows the same discovery report used by the CLI. Review matched, repeated, missing, unmatched, and invalid entries before confirming ingestion.

## Container deployment

Docker Compose uses PostgreSQL and requires the same persistent token:

```bash
export DASHBOARD_INGEST_TOKEN='<PERSISTENT_TOKEN>'
uv run poe up
```

Stop with `uv run poe down`. `uv run poe reset` also removes the development database volume.

## Development checks

```bash
uv run poe test
uv run poe check
uv run poe security
```
