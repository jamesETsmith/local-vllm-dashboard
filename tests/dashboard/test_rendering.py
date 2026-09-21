import json
from datetime import UTC, date, datetime, timedelta
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


def dashboard_client(*, populated: bool = True, public_url: str | None = None) -> TestClient:
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
            performance_completed_at = datetime.combine(
                date.today() - timedelta(days=7),
                datetime.min.time(),
                tzinfo=UTC,
            )
            performance = performance.model_copy(
                update={
                    "run": performance.run.model_copy(
                        update={
                            "started_at": performance_completed_at - timedelta(minutes=15),
                            "completed_at": performance_completed_at,
                        }
                    )
                }
            )
            performance = performance.model_copy(
                update={"idempotency_key": performance.calculated_idempotency_key()}
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
                completed_at=datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC),
            )
            BundleRepository(session).save(
                accuracy,
                artifact_contents(accuracy, (recipe, accuracy_result)),
            )
    app = create_app(
        Settings(
            database_url="sqlite+pysqlite:///:memory:",
            ingest_token="test-token",
            public_url=public_url,
        ),
        factory,
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


def test_public_url_is_used_in_help_and_agent_instructions() -> None:
    with dashboard_client(public_url="https://benchmarks.example.com:8443") as client:
        help_page = client.get("/dashboard/help")
        agent_guide = client.get("/llms.txt")

    assert "https://benchmarks.example.com:8443/mcp/" in help_page.text
    assert "https://benchmarks.example.com:8443/openapi.json" in help_page.text
    assert "https://benchmarks.example.com:8443/mcp/" in agent_guide.text
    assert "https://benchmarks.example.com:8443/openapi.json" in agent_guide.text


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
    payload = response.text.split('id="performance-chart-data">', 1)[1].split("</script>", 1)[0]
    point = json.loads(payload)[0]["points"][0]
    assert point["tensor_parallel_size"] == 4
    assert point["server_settings_available"] is True
    assert point["decode_context_parallel_size"] == 2
    assert point["speculative_decode"] == "tokens: 3"
    assert point["kv_cache_offload"] == "size: 16, backend: native"
    assert "undefined" not in payload
    assert "https://github.com/jamesETsmith/local-vllm-dashboard" in response.text
    assert "Raw Data Table" in response.text
    assert "Normalized results" not in response.text
    chart_script = client.get("/dashboard/static/performance-chart.js")
    assert chart_script.status_code == 200
    assert "ignoredTraceFields" in chart_script.text
    assert "data-chart-zoom-in" in chart_script.text
    assert 'addEventListener("wheel"' in chart_script.text
    assert 'addEventListener("mousedown"' in chart_script.text
    assert "panDomain" in chart_script.text
    assert "model-chart-legend" in chart_script.text
    assert "traceSymbols" in chart_script.text
    assert "traceDate" in chart_script.text
    assert "tooltip.offsetHeight" in chart_script.text
    assert "window.innerHeight" in chart_script.text
    assert "configurationItems" in chart_script.text
    assert 'value ?? "unknown"' in chart_script.text
    assert "TP:" in chart_script.text
    assert "EP:" in chart_script.text
    assert "Spec decode:" in chart_script.text
    assert "DCP:" in chart_script.text
    assert "KV cache offload:" in chart_script.text
    assert "<ul>" in chart_script.text
    assert "bundle_id: point.bundle_id" not in chart_script.text
    assert "point.bundle_id" in chart_script.text
    assert "tickValues(xMin, xMax" in chart_script.text
    assert "/static/performance-chart.js?v=2" in response.text


def test_accuracy_dashboard_renders_task_configuration() -> None:
    with dashboard_client() as client:
        response = client.get("/dashboard/?tab=accuracy&task=gsm8k")

    assert response.status_code == 200
    assert "Accuracy" in response.text
    assert "gsm8k" in response.text
    assert "5-shot" in response.text


def test_dashboard_defaults_to_last_four_weeks() -> None:
    today = date.today()
    four_weeks_ago = today - timedelta(weeks=4)

    with dashboard_client() as client:
        response = client.get("/dashboard/")

    assert response.status_code == 200
    assert f'name="start_date" value="{four_weeks_ago.isoformat()}"' in response.text
    assert f'name="end_date" value="{today.isoformat()}"' in response.text
    assert "No performance results" not in response.text


def test_dashboard_filters_results_by_completion_date_range() -> None:
    today = date.today()

    with dashboard_client() as client:
        matching = client.get(
            f"/dashboard/?start_date={today.isoformat()}&end_date={today.isoformat()}"
        )
        missing = client.get("/dashboard/?start_date=2099-01-01")
        invalid = client.get(f"/dashboard/?start_date=not-a-date&end_date={today.isoformat()}")
        all_dates = client.get("/dashboard/?start_date=&end_date=")

    assert matching.status_code == 200
    assert f'name="start_date" value="{today.isoformat()}"' in matching.text
    assert f'name="end_date" value="{today.isoformat()}"' in matching.text
    assert "No performance results" in matching.text
    assert missing.status_code == 200
    assert "No performance results" in missing.text
    assert invalid.status_code == 200
    assert 'name="start_date" value=""' in invalid.text
    assert "No performance results" not in all_dates.text


def test_raw_data_download_applies_completion_date_range() -> None:
    performance_date = date.today() - timedelta(days=7)

    with dashboard_client() as client:
        matching = client.get(
            f"/dashboard/raw-data.csv?start_date={performance_date.isoformat()}"
            f"&end_date={performance_date.isoformat()}"
        )
        missing = client.get("/dashboard/raw-data.csv?start_date=2099-01-01")

    assert len(matching.text.splitlines()) == 2
    assert len(missing.text.splitlines()) == 1


def test_custom_comparison_renders_selectable_results_and_chart_controls() -> None:
    with dashboard_client() as client:
        dashboard = client.get("/dashboard/")
        response = client.get("/dashboard/comparison")

    assert response.status_code == 200
    assert 'href="/dashboard/comparison"' in dashboard.text
    assert "Custom Comparison" in response.text
    assert "actual vLLM command-line arguments" in response.text
    assert "--enable-expert-parallel" in response.text
    assert "--gpu-memory-utilization 0.95" in response.text
    assert 'id="comparison-search-help"' in response.text
    assert 'aria-describedby="comparison-search-help"' in response.text
    assert 'role="tooltip"' in response.text
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
    assert 'data-comparison-chart-type="bar"' in response.text
    assert 'data-comparison-chart-type="line"' in response.text
    assert 'id="comparison-chart-data"' in response.text
    assert "custom-comparison.js" in response.text
    chart_script = client.get("/dashboard/static/custom-comparison.js")
    assert chart_script.status_code == 200
    assert "activeChartType" in chart_script.text
    assert 'element("polyline"' in chart_script.text
    assert 'element("circle"' in chart_script.text


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
    assert 'id="raw-data-search"' in response.text
    assert 'aria-describedby="raw-data-search-help"' in response.text
    assert "actual vLLM command-line arguments" in response.text
    assert 'id="raw-data-filter-count"' in response.text
    assert 'id="raw-data-filter-empty"' in response.text
    assert "data-search-base=" in response.text
    assert "data-search-config=" in response.text
    assert "num_warmups" in response.text
    assert "enable-prefix-caching" in response.text
    assert "raw-data-search.js" in response.text
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
    assert "YAML Config" in response.text
    assert "Reproduce Results" in response.text
    assert "Extracted Data JSON" in response.text
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
    ordered_sections = (
        'id="summary"',
        'id="perf-data"',
        'id="yaml-config"',
        'id="reproduce-results"',
        'id="extracted-data"',
    )
    positions = [response.text.index(section) for section in ordered_sections]
    assert positions == sorted(positions)


def test_performance_dashboard_renders_multi_select_filters() -> None:
    with dashboard_client() as client:
        response = client.get(
            "/dashboard/?hardware=MI355X&hardware=H200&prefix_cache_tokens=40000&concurrency=4"
        )
        script = client.get("/dashboard/static/auto-filters.js")

    assert response.status_code == 200
    assert response.text.count('class="filter-dropdown"') == 7
    assert response.text.count('class="filter-chevron"') == 7
    assert response.text.count("Uncheck all") == 7
    assert "Apply filters" not in response.text
    assert 'name="hardware" value="MI355X" checked' in response.text
    assert 'name="prefix_cache_tokens" value="40000" checked' in response.text
    assert 'name="concurrency" value="4" checked' in response.text
    assert "2 selected" in response.text
    assert 'href="?tab=runs"' in response.text
    assert "hardware=MI355X&amp;tab=runs" not in response.text
    assert 'name="workload"' not in response.text
    assert script.status_code == 200
    assert 'querySelectorAll(".filter-dropdown")' in script.text
    assert 'querySelector(".filter-clear")' in script.text
    assert "checkbox.checked = false" in script.text
    assert 'checkbox.addEventListener("change", submitFilters)' in script.text
    assert "querySelectorAll('input[type=\"date\"]')" in script.text
    assert 'dateInput.addEventListener("change", submitFilters)' in script.text
    assert "submitFilters();" in script.text


def test_dashboard_has_clear_empty_state() -> None:
    with dashboard_client(populated=False) as client:
        response = client.get("/dashboard/")

    assert response.status_code == 200
    assert "No performance results" in response.text
