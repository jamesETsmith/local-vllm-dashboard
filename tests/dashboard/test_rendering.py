from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from local_vllm_dashboard.adapter import build_accuracy_bundle, build_performance_bundle
from local_vllm_dashboard.api import Settings, create_app
from local_vllm_dashboard.artifacts import artifact_contents
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
            performance = build_performance_bundle(recipe, result)
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
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"), factory)
    return TestClient(app)


def test_root_redirects_to_dashboard() -> None:
    with dashboard_client() as client:
        response = client.get("/", follow_redirects=False)
        favicon = client.get("/favicon.ico")

    assert response.status_code == 307
    assert response.headers["location"] == "/dashboard/"
    assert favicon.status_code == 204


def test_performance_dashboard_renders_normalized_results() -> None:
    with dashboard_client() as client:
        response = client.get("/dashboard/")

    assert response.status_code == 200
    assert "Performance" in response.text
    assert "Throughput by concurrency" in response.text
    assert "performance-chart-data" in response.text
    assert "ISL 50000" in response.text
    assert "Prefix 40000" in response.text
    assert "https://github.com/jamesETsmith/local-vllm-dashboard" in response.text
    assert "prefix-cache-performance-mi355x" in response.text
    assert "token/s/gpu" in response.text
    assert "39 failed" in response.text


def test_accuracy_dashboard_renders_task_configuration() -> None:
    with dashboard_client() as client:
        response = client.get("/dashboard/?tab=accuracy&task=gsm8k")

    assert response.status_code == 200
    assert "Accuracy" in response.text
    assert "gsm8k" in response.text
    assert "5-shot" in response.text


def test_runs_dashboard_renders_provenance() -> None:
    with dashboard_client() as client:
        response = client.get("/dashboard/?tab=runs")

    assert response.status_code == 200
    assert "Runs &amp; Data" in response.text
    assert "example-registry/vllm-openai:test" in response.text
    assert "artifact references" in response.text
    assert 'class="run-row"' in response.text
    assert "run-links.js" in response.text


def test_run_detail_renders_full_configuration() -> None:
    with dashboard_client() as client:
        dashboard = client.get("/dashboard/")
        marker = 'data-href="/dashboard/runs/'
        bundle_id = dashboard.text.split(marker, 1)[1].split('"', 1)[0]
        response = client.get(f"/dashboard/runs/{bundle_id}")

    assert response.status_code == 200
    assert "Run provenance" in response.text
    assert "&#34;max_concurrency&#34;: 4" in response.text
    assert "&#34;prefix_cache_tokens&#34;: 40000" in response.text
    assert "Complete submitted bundle" in response.text
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
        response = client.get("/dashboard/?hardware=MI355X&concurrency=4")

    assert response.status_code == 200
    assert "<option selected>MI355X</option>" in response.text
    assert "<option selected>4</option>" in response.text
    assert 'name="workload"' not in response.text


def test_dashboard_has_clear_empty_state() -> None:
    with dashboard_client(populated=False) as client:
        response = client.get("/dashboard/")

    assert response.status_code == 200
    assert "No performance results" in response.text
