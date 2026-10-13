# Using the vLLM Results Dashboard

The dashboard provides human-readable comparisons and machine-readable access to the same standardized benchmark results. Replace `{base_url}` with the address of this deployment, without a trailing slash.

## Install the client

Everything needed to publish or reproduce results is in the `local-vllm-dashboard` client. Install it once on a benchmark or repro host:

```bash
uv tool install "git+https://github.com/jamesETsmith/local-vllm-dashboard"
```

Then run commands with `local-vllm-dashboard ...`, or use `uvx --from git+https://github.com/jamesETsmith/local-vllm-dashboard local-vllm-dashboard ...` for a one-off run without installing.

## Reproducing a result

Every stored result keeps the exact perf-eval workload YAML and the original benchmark result JSON used to produce it. To rebuild a run, install perf-eval, download the repro bundle, then run it.

### 1. Install perf-eval

Clone [perf-eval](https://github.com/vllm-project/perf-eval) onto a GPU host with Docker and vLLM available:

```bash
git clone https://github.com/vllm-project/perf-eval
cd perf-eval
```

### 2. Download the repro bundle

Select a row or chart point in the dashboard and copy the command under **Reproduce Results**, or use the run's `bundle_id`:

```bash
local-vllm-dashboard reproduce \
  --endpoint {base_url} \
  --bundle-id <BUNDLE_ID> \
  --output ./reproduction
```

This writes the workload YAML, the original result JSON, and a `reproduction.json` summary into `./reproduction`.

### 3. Run the workload

Copy the workload YAML into the perf-eval `workloads/` directory and run it from the perf-eval root:

```bash
cp ./reproduction/<workload>.yaml perf-eval/workloads/
cd perf-eval
./lib/run.sh workloads/<workload>.yaml
```

`./lib/run.sh` starts the vLLM server from the recipe's image, runs the benchmark and accuracy tasks, and writes `results/<name>/`. Compare the new raw JSON against the original result saved in the repro bundle.

## For agents

Agents do not automatically discover this service. Give the agent the REST API or configure the MCP endpoint explicitly. The query interfaces are read-only and require no application token, but the deployment network or proxy may enforce access controls.

MCP endpoint:

```text
{base_url}/mcp/
```

The MCP server describes its own tools and schemas after a client connects. It supports configuration search, discovery of available filter values, and retrieval of stored reproduction recipes and commands for a given bundle.

### Reproducing results

To reproduce a stored result, search for its configuration, then fetch the reproduction bundle by `bundle_id`. The response contains the exact stored workload YAML and original result JSON, plus ready-to-run commands.

Use the MCP tool `get_reproduction`:

```json
{ "bundle_id": "<BUNDLE_ID>" }
```

Or call the REST endpoint directly:

```text
GET {base_url}/api/v1/configurations/{bundle_id}/reproduction
```

Each response includes:

- `run`: bundle id, workload name, model, hardware, vLLM image and commit, and dependency revisions.
- `artifacts`: the workload recipe and raw result files with their content, media type, and digest.
- `perf_eval_command`: the perf-eval invocation, for example `./lib/run.sh <workload>.yaml`.
- `recipes`: per-configuration `docker run` server and `vllm bench serve` benchmark commands.

Write `artifacts` to disk and run `perf_eval_command` after installing [perf-eval](https://github.com/vllm-project/perf-eval), or use the `local-vllm-dashboard reproduce` command described under **Reproducing a result**.

### Crush

Add this entry under `mcp` in a project or global `crush.json`:

```json
{
  "mcp": {
    "local-vllm-dashboard": {
      "type": "http",
      "url": "{base_url}/mcp/"
    }
  }
}
```

### Cursor

Add this entry to `.cursor/mcp.json` in a project or to the Cursor user MCP configuration:

```json
{
  "mcpServers": {
    "local-vllm-dashboard": {
      "type": "http",
      "url": "{base_url}/mcp/"
    }
  }
}
```

### Claude Code

Register the remote HTTP server:

```bash
claude mcp add --transport http local-vllm-dashboard {base_url}/mcp/
```

## REST API

Interactive OpenAPI documentation:

```text
{base_url}/docs
```

Machine-readable OpenAPI schema:

```text
{base_url}/openapi.json
```

Search benchmark configurations:

```text
GET {base_url}/api/v1/configurations
```

Exact-match query parameters include `hardware`, `model`, `precision`, `input_tokens`, `output_tokens`, `prefix_cache_tokens`, and `concurrency`. Results use bounded `limit` and `offset` pagination.

Example:

```bash
curl "{base_url}/api/v1/configurations?hardware=MI355X&model=example-org%2Fexample-model&limit=20"
```

Discover valid filter values:

```text
GET {base_url}/api/v1/configuration-filters
```

Fetch the stored workload recipe, original result artifacts, and ready-to-run commands for a single result:

```text
GET {base_url}/api/v1/configurations/{bundle_id}/reproduction
```

Agents that can read OpenAPI should use `{base_url}/openapi.json` as the authoritative endpoint and response contract instead of relying on examples in prose.

<!--
Discovery and source of truth

This guide is the source for the Help tab and /llms.txt. Edit docs/USING_THE_DASHBOARD.md rather than copying usage instructions into templates. REST schemas and parameter constraints come from the FastAPI/Pydantic definitions and are published automatically through /docs and /openapi.json. MCP tool names, descriptions, and input schemas come from the registered MCP tools.

/llms.txt is a convenience for agents that support that convention. It does not replace explicit MCP client configuration or the OpenAPI contract.
-->
