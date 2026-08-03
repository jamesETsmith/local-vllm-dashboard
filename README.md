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

Generate the ingestion token once. Reuse it across restarts and share it only with approved publishing hosts.

```bash
umask 077
cat > .env <<EOF
DASHBOARD_DATABASE_URL=sqlite+pysqlite:///./dashboard.db
DASHBOARD_INGEST_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
EOF
```

Load the configuration:

```bash
set -a
source .env
set +a
```

### 3. Initialize and start

```bash
uv run local-vllm-dashboard init-db
uv run uvicorn local_vllm_dashboard.api.server:app \
  --host <VPN_IP> \
  --port 8010
```

Find `<VPN_IP>` with `ip -brief address`. Open:

```text
http://<VPN_IP>:8010/dashboard/
```

The dashboard is readable on the VPN. Writes require the token. Keep the `.env` file private and reuse the same token across service restarts.

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
  --endpoint http://<VPN_IP>:8010
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

Use `--container <NAME_OR_ID>` when automatic container discovery is ambiguous. The archive contains matched workload and result files plus revision metadata extracted with the same vLLM and ROCm AITER detection used by direct ingestion. Upload the resulting archive through the browser. Dependency commits are stored as queryable run metadata and shown in the Runs & Data table and run detail view.

## Browser upload

Open `http://<VPN_IP>:8010/dashboard/upload` or select **Upload results** on the dashboard. Enter the ingestion token, then choose either:

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
