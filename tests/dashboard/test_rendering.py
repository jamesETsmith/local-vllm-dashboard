from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from local_vllm_dashboard.adapter import build_accuracy_bundle, build_performance_bundle
from local_vllm_dashboard.api import Settings, create_app
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
            BundleRepository(session).save(
                build_performance_bundle(
                    FIXTURES / "prefix_cache_workload.yaml",
                    FIXTURES / "prefix_cache_partial_failure_bench.json",
                )
            )
            BundleRepository(session).save(
                build_accuracy_bundle(
                    FIXTURES / "prefix_cache_workload.yaml",
                    FIXTURES / "lm_eval_results.json",
                    task="gsm8k",
                    completed_at=datetime(2026, 7, 23, tzinfo=UTC),
                )
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


def test_dashboard_preserves_filters_in_rendered_form() -> None:
    with dashboard_client() as client:
        response = client.get("/dashboard/?hardware=MI355X&concurrency=4")

    assert response.status_code == 200
    assert "<option selected>MI355X</option>" in response.text
    assert "<option selected>4</option>" in response.text


def test_dashboard_has_clear_empty_state() -> None:
    with dashboard_client(populated=False) as client:
        response = client.get("/dashboard/")

    assert response.status_code == 200
    assert "No performance results" in response.text
