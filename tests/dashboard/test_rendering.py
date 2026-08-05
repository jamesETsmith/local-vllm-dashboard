from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from local_vllm_dashboard.adapter import build_accuracy_bundle, build_performance_bundle
from local_vllm_dashboard.api import Settings, create_app
from local_vllm_dashboard.artifacts import artifact_contents
from local_vllm_dashboard.container_revisions import ContainerRevisions
from local_vllm_dashboard.db import Base, BundleRepository, make_session_factory

FIXTURES = Path(__file__).parents[1] / "fixtures" / "perf_eval"


def dashboard_client(*, populated: bool = True) -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    if populated:
        with factory() as session:
            recipe = FIXTURES / "prefix_cache_workload.yaml"
            result = FIXTURES / "prefix_cache_partial_failure_bench.json"
            performance = build_performance_bundle(
                recipe,
                result,
                container_revisions=ContainerRevisions(
                    vllm_commit="abcdef0",
                    aiter_commit="fedcba0",
                ),
            )
            BundleRepository(session).save(
                performance,
                artifact_contents(performance, (recipe, result)),
            )
            accuracy_result = FIXTURES / "lm_eval_results.json"
            accuracy = build_accuracy_bundle(
                recipe,
                accuracy_result,
                task="gsm8k",
                completed_at=datetime(2026, 7, 23, tzinfo=UTC),
            )
            BundleRepository(session).save(
                accuracy,
                artifact_contents(accuracy, (recipe, accuracy_result)),
            )
    app = create_app(
        Settings(database_url="sqlite+pysqlite:///:memory:", ingest_token="test-token"), factory
    )
    return TestClient(app)


def test_root_redirects_to_dashboard() -> None:
    with dashboard_client() as client:
        response = client.get("/", follow_redirects=False)
        favicon = client.get("/favicon.ico")

    assert response.status_code == 307
    assert response.headers["location"] == "/dashboard/"
    assert favicon.status_code == 204


def test_help_and_agent_instructions_share_usage_documentation() -> None:
    with dashboard_client() as client:
        dashboard = client.get("/dashboard/")
        help_page = client.get("/dashboard/help")
        agent_guide = client.get("/llms.txt")

    assert 'href="/dashboard/help"' in dashboard.text
    assert help_page.status_code == 200
    assert "For people" in help_page.text
    assert "For agents" in help_page.text
    assert "Crush" in help_page.text
    assert "Cursor" in help_page.text
    assert "Claude Code" in help_page.text
    assert "http://testserver/mcp/" in help_page.text
    assert "http://testserver/openapi.json" in help_page.text
    assert "Discovery and source of truth" not in help_page.text
    assert 'class="help-toc"' in help_page.text
    assert 'href="#for-people"' in help_page.text
    assert 'href="#for-agents"' in help_page.text
    assert 'href="#rest-api"' in help_page.text
    assert agent_guide.status_code == 200
    assert agent_guide.headers["content-type"].startswith("text/plain")
    assert "# Using the vLLM Results Dashboard" in agent_guide.text
    assert "http://testserver/mcp/" in agent_guide.text
    assert "http://testserver/openapi.json" in agent_guide.text
    assert "Discovery and source of truth" not in agent_guide.text


def test_performance_dashboard_renders_normalized_results() -> None:
    with dashboard_client() as client:
        response = client.get("/dashboard/")

    assert response.status_code == 200
    assert "Performance" in response.text
    assert "Compare standardized performance and accuracy results" not in response.text
    assert "Total token throughput by model" in response.text
    assert "performance-chart-data" in response.text
    assert 'data-chart-metric="total_token_throughput_per_gpu"' in response.text
    assert 'data-chart-metric="output_token_throughput_per_gpu"' in response.text
    assert 'data-chart-metric="mean_ttft"' in response.text
    assert 'data-chart-metric="mean_tpot"' in response.text
    assert "Throughput remains normalized per GPU" in response.text
    assert '"input_tokens": 50000' in response.text
    assert '"prefix_cache_tokens": 40000' in response.text
    assert "https://github.com/jamesETsmith/local-vllm-dashboard" in response.text
    assert "Raw Data Table" in response.text
    assert "Normalized results" not in response.text


def test_accuracy_dashboard_renders_task_configuration() -> None:
    with dashboard_client() as client:
        response = client.get("/dashboard/?tab=accuracy&task=gsm8k")

    assert response.status_code == 200
    assert "Accuracy" in response.text
    assert "gsm8k" in response.text
    assert "5-shot" in response.text


def test_custom_comparison_renders_selectable_results_and_chart_controls() -> None:
    with dashboard_client() as client:
        dashboard = client.get("/dashboard/")
        response = client.get("/dashboard/comparison")

    assert response.status_code == 200
    assert 'href="/dashboard/comparison"' in dashboard.text
    assert "Custom Comparison" in response.text
    assert 'class="comparison-result"' in response.text
    assert 'data-comparison-result="0:0"' in response.text
    assert "example-org/example-model" in response.text
    assert "MI355X" in response.text
    assert "ISL 50000" in response.text
    assert (
        'data-search-base="example-org/example-model mi355x quantized tp 4 dp 1 ep off '
        'expert-parallel off"' in response.text
    )
    assert "data-search-config=" in response.text
    assert "num_warmups" in response.text
    assert "enable-prefix-caching" in response.text
    assert 'id="comparison-filter-count"' in response.text
    assert 'id="comparison-filter-empty"' in response.text
    assert 'id="comparison-result-preview"' in response.text
    assert 'aria-describedby="comparison-result-preview"' in response.text
    assert 'tabindex="0"' in response.text
    assert 'data-comparison-metric="total_token_throughput_per_gpu"' in response.text
    assert 'id="comparison-chart-data"' in response.text
    assert "custom-comparison.js" in response.text


def test_custom_comparison_has_clear_empty_state() -> None:
    with dashboard_client(populated=False) as client:
        response = client.get("/dashboard/comparison")

    assert response.status_code == 200
    assert "No performance results to compare" in response.text


def test_runs_dashboard_renders_provenance() -> None:
    with dashboard_client() as client:
        response = client.get("/dashboard/?tab=runs")

    assert response.status_code == 200
    assert "Raw Data Table" in response.text
    assert "Flattened observations" in response.text
    assert "Download selection" in response.text
    assert 'formaction="/dashboard/raw-data.csv"' in response.text
    assert "Total tok/s/GPU" in response.text
    assert "Mean TTFT (s)" in response.text
    assert "dataframe-table" in response.text
    assert "auto-filters.js" in response.text
    assert "Apply filters" not in response.text
    assert "Reset filters" in response.text
    assert "TP" in response.text
    assert "EP" in response.text
    assert "example-registry/vllm-openai:test" in response.text
    assert "Dependency commits" in response.text
    assert "aiter=fedcba0" in response.text
    assert 'class="run-row"' in response.text
    assert "run-links.js" in response.text


def test_raw_data_download_exports_filtered_csv() -> None:
    with dashboard_client() as client:
        response = client.get(
            "/dashboard/raw-data.csv?hardware=MI355X&model=example-org/example-model"
        )
        missing = client.get("/dashboard/raw-data.csv?hardware=H200")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="vllm-raw-data.csv"'
    assert "total_token_throughput_per_gpu" in response.text
    assert "example-org/example-model" in response.text
    assert "aiter=fedcba0" in response.text
    assert len(response.text.splitlines()) == 2
    assert len(missing.text.splitlines()) == 1


def test_run_detail_renders_full_configuration() -> None:
    with dashboard_client() as client:
        dashboard = client.get("/dashboard/?tab=runs")
        marker = 'data-href="/dashboard/runs/'
        bundle_id = dashboard.text.split(marker, 1)[1].split('"', 1)[0]
        response = client.get(f"/dashboard/runs/{bundle_id}")

    assert response.status_code == 200
    assert "Run provenance" in response.text
    assert "AITER commit" in response.text
    assert "fedcba0" in response.text
    assert "Perf Data" in response.text
    assert "Reproduce Results" in response.text
    assert "local-vllm-dashboard Info" in response.text
    assert "On this page" in response.text
    assert 'href="#perf-data"' in response.text
    assert 'href="#reproduce-results"' in response.text
    assert 'class="toc-emphasis"' in response.text
    assert "&#34;max_concurrency&#34;: 4" in response.text
    assert "&#34;prefix_cache_tokens&#34;: 40000" in response.text
    assert "Complete submitted data" in response.text
    assert "perf-eval workload YAML" in response.text
    assert "Transformed / extracted source data" in response.text
    assert "prefix_cache_workload.yaml" in response.text
    assert "Run with perf-eval" in response.text
    assert "lib/run.sh" in response.text
    assert "prefix_cache_workload.yaml" in response.text
    assert "Copy to clipboard" in response.text
    assert "highlighted-code" in response.text
    assert "copy-code.js" in response.text


def test_dashboard_preserves_filters_in_rendered_form() -> None:
    with dashboard_client() as client:
        response = client.get("/dashboard/?hardware=MI355X&prefix_cache_tokens=40000&concurrency=4")

    assert response.status_code == 200
    assert "<option selected>MI355X</option>" in response.text
    assert "<option selected>4</option>" in response.text
    assert 'href="?tab=runs"' in response.text
    assert "hardware=MI355X&amp;tab=runs" not in response.text
    assert 'name="prefix_cache_tokens"' in response.text
    assert '<option value="40000" selected>40000</option>' in response.text
    assert 'name="workload"' not in response.text


def test_dashboard_has_clear_empty_state() -> None:
    with dashboard_client(populated=False) as client:
        response = client.get("/dashboard/")

    assert response.status_code == 200
    assert "No performance results" in response.text
