from pathlib import Path
from typing import Any, cast

import anyio
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from local_vllm_dashboard.adapter import build_performance_bundle
from local_vllm_dashboard.api import Settings, create_app
from local_vllm_dashboard.artifacts import artifact_contents
from local_vllm_dashboard.db import Base, BundleRepository, make_session_factory
from local_vllm_dashboard.query import QueryService, create_mcp_server

FIXTURES = Path(__file__).parents[1] / "fixtures" / "perf_eval"


def query_client() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    recipe = FIXTURES / "prefix_cache_workload.yaml"
    result = FIXTURES / "prefix_cache_partial_failure_bench.json"
    bundle = build_performance_bundle(recipe, result)
    with factory() as session:
        BundleRepository(session).save(bundle, artifact_contents(bundle, (recipe, result)))
    app = create_app(
        Settings(database_url="sqlite+pysqlite:///:memory:", ingest_token="test-token"),
        factory,
    )
    app.state.query_session_factory = factory
    return TestClient(app)


def test_query_api_filters_and_paginates_configurations() -> None:
    with query_client() as client:
        response = client.get(
            "/api/v1/configurations",
            params={
                "hardware": "MI355X",
                "model": "example-org/example-model",
                "input_tokens": 50000,
                "output_tokens": 1000,
                "prefix_cache_tokens": 40000,
                "concurrency": 4,
                "precision": "quantized",
                "limit": 1,
            },
        )
        missing = client.get("/api/v1/configurations", params={"hardware": "H200"})

    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 1
    assert page["limit"] == 1
    assert page["offset"] == 0
    assert page["items"][0]["hardware"] == "MI355X"
    assert page["items"][0]["model"] == "example-org/example-model"
    assert page["items"][0]["metrics"]
    assert missing.json()["items"] == []


def test_query_api_lists_available_filter_values_and_openapi_schema() -> None:
    with query_client() as client:
        response = client.get("/api/v1/configuration-filters")
        schema = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["hardware"] == ["MI355X"]
    assert response.json()["models"] == ["example-org/example-model"]
    assert "/api/v1/configurations" in schema.json()["paths"]
    assert "/api/v1/configuration-filters" in schema.json()["paths"]


def test_query_api_rejects_unbounded_page_sizes() -> None:
    with query_client() as client:
        response = client.get("/api/v1/configurations?limit=101")

    assert response.status_code == 422


def test_mcp_exposes_shared_configuration_queries() -> None:
    client = query_client()
    app = client.app
    query_service = QueryService(app.state.query_session_factory)
    server = create_mcp_server(
        query_service,
        allowed_hosts=("testserver",),
        allowed_origins=("http://testserver",),
    )

    async def query_mcp() -> None:
        tools = await server.list_tools()
        _, page_result = await server.call_tool(
            "search_configurations",
            {"hardware": "MI355X", "limit": 1},
        )
        _, filter_result = await server.call_tool("list_configuration_filters", {})
        page = cast(dict[str, Any], page_result)
        filters = cast(dict[str, Any], filter_result)

        assert {tool.name for tool in tools} == {
            "list_configuration_filters",
            "search_configurations",
        }
        assert page["total"] == 1
        assert page["items"][0]["hardware"] == "MI355X"
        assert filters["hardware"] == ["MI355X"]

    anyio.run(query_mcp)


def test_mcp_transport_accepts_configured_hosts_and_rejects_others() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    app = create_app(
        Settings(
            database_url="sqlite+pysqlite:///:memory:",
            ingest_token="test-token",
            mcp_allowed_hosts=("benchmarks.example.com:*",),
            mcp_allowed_origins=("https://benchmarks.example.com:*",),
        ),
        factory,
    )

    with TestClient(app) as client:
        allowed = client.get(
            "/mcp/",
            headers={"Host": "benchmarks.example.com:8010"},
        )
        rejected_host = client.get(
            "/mcp/",
            headers={"Host": "untrusted.example.com:8010"},
        )
        rejected_origin = client.get(
            "/mcp/",
            headers={
                "Host": "benchmarks.example.com:8010",
                "Origin": "https://untrusted.example.com:8010",
            },
        )

    assert allowed.status_code == 406
    assert rejected_host.status_code == 421
    assert rejected_origin.status_code == 403
