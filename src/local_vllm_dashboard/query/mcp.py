from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette

from local_vllm_dashboard.query.models import ConfigurationFilters
from local_vllm_dashboard.query.service import QueryService


def create_mcp_server(service: QueryService) -> FastMCP:
    server = FastMCP(
        "Local vLLM Dashboard",
        instructions="Discover and query standardized local vLLM benchmark configurations.",
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
    )

    @server.tool()
    def search_configurations(
        hardware: str | None = None,
        model: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        prefix_cache_tokens: int | None = None,
        concurrency: int | None = None,
        precision: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, object]:
        """Search benchmark configurations and their recorded metrics."""
        bounded_limit = min(max(limit, 1), 100)
        bounded_offset = max(offset, 0)
        page = service.configurations(
            ConfigurationFilters(
                hardware=hardware,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                prefix_cache_tokens=prefix_cache_tokens,
                concurrency=concurrency,
                precision=precision,
            ),
            limit=bounded_limit,
            offset=bounded_offset,
        )
        return page.model_dump(mode="json")

    @server.tool()
    def list_configuration_filters() -> dict[str, object]:
        """List available values for benchmark configuration filters."""
        return service.configuration_filters().model_dump(mode="json")

    return server


def create_mcp_app(server: FastMCP) -> Starlette:
    return server.streamable_http_app()
