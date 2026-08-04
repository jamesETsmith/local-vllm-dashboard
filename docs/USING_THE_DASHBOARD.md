# Using the vLLM Results Dashboard

The dashboard provides human-readable comparisons and machine-readable access to the same standardized benchmark results. Replace `{base_url}` with the address of this deployment, without a trailing slash.

## For people

- **Performance** compares configurations within each model. Select total token throughput, output token throughput, TTFT, or TPOT. Throughput is normalized per GPU.
- **Accuracy** shows task scores with the task configuration beside each result.
- **Raw Data Table** exposes flattened performance observations and downloads the current hardware/model selection as CSV.
- Select a chart point or table row to inspect full configuration, provenance, dependency revisions, and stored source artifacts.
- **Upload results** accepts a packaged archive or matching workload YAML and result JSON files. Uploading requires the ingestion token.

## For agents

Agents do not automatically discover this service. Give the agent the REST API or configure the MCP endpoint explicitly. The query interfaces are read-only and require no application token, but the deployment network or proxy may enforce access controls.

MCP endpoint:

```text
{base_url}/mcp/
```

The MCP server describes its own tools and schemas after a client connects. It currently supports configuration search and discovery of available filter values.

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

Agents that can read OpenAPI should use `{base_url}/openapi.json` as the authoritative endpoint and response contract instead of relying on examples in prose.

<!--
Discovery and source of truth

This guide is the source for the Help tab and /llms.txt. Edit docs/USING_THE_DASHBOARD.md rather than copying usage instructions into templates. REST schemas and parameter constraints come from the FastAPI/Pydantic definitions and are published automatically through /docs and /openapi.json. MCP tool names, descriptions, and input schemas come from the registered MCP tools.

/llms.txt is a convenience for agents that support that convention. It does not replace explicit MCP client configuration or the OpenAPI contract.
-->
