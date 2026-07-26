from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from local_vllm_dashboard.adapter import build_accuracy_bundle, build_performance_bundle
from local_vllm_dashboard.artifacts import artifact_contents
from local_vllm_dashboard.dashboard.models import DashboardFilters
from local_vllm_dashboard.dashboard.repository import DashboardRepository
from local_vllm_dashboard.db import Base, BundleRepository, make_engine, make_session_factory

FIXTURES = Path(__file__).parents[1] / "fixtures" / "perf_eval"


def dashboard_repository() -> DashboardRepository:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
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
    return DashboardRepository(session)


def test_repository_loads_all_dashboard_views() -> None:
    data = dashboard_repository().load()

    assert len(data.performance) == 1
    assert len(data.accuracy) == 1
    assert len(data.runs) == 2
    assert data.options.hardware == ("MI355X",)
    assert data.options.tasks == ("gsm8k",)
    assert data.options.prefix_cache_tokens == (40000,)
    assert data.performance[0].failed_requests == 39
    assert data.accuracy[0].fewshot == 5


def test_repository_loads_full_run_detail() -> None:
    repository = dashboard_repository()
    bundle_id = repository.load().performance[0].bundle_id

    detail = repository.detail(bundle_id)

    assert detail is not None
    assert detail.run.bundle_id == bundle_id
    assert '"max_concurrency": 4' in detail.configuration_json[0]
    assert '"prefix_cache_tokens": 40000' in detail.configuration_json[0]
    assert len(detail.metrics[0]) > 1
    assert len(detail.artifacts) == 2
    assert detail.artifacts[0].text
    workload_artifact = next(
        artifact for artifact in detail.artifacts if artifact.role == "workload_recipe"
    )
    assert "serve_args: >-" in workload_artifact.text
    assert "    --tensor-parallel-size 4\n" in workload_artifact.text
    assert "    --trust-remote-code\n" in workload_artifact.text
    assert "    --max-model-len 65536\n" in workload_artifact.text
    assert "50k-in-1k-out-40k-cached-conc-4" in workload_artifact.text
    assert {artifact.role for artifact in detail.artifacts} == {
        "raw_bench_result",
        "workload_recipe",
    }
    assert repository.detail(UUID(int=0)) is None


def test_repository_filters_performance_settings() -> None:
    repository = dashboard_repository()

    matching = repository.load(
        DashboardFilters(hardware="MI355X", concurrency=4, prefix_cache_tokens=40000)
    )
    missing = repository.load(DashboardFilters(hardware="H200"))

    assert len(matching.performance) == 1
    assert not missing.performance
    assert not missing.accuracy
    assert not missing.runs
    assert matching.options.hardware == ("MI355X",)
    assert not repository.load(DashboardFilters(prefix_cache_tokens=0)).performance


def test_repository_filters_accuracy_task() -> None:
    repository = dashboard_repository()

    matching = repository.load(DashboardFilters(task="gsm8k"))
    missing = repository.load(DashboardFilters(task="aime25"))

    assert len(matching.accuracy) == 1
    assert not missing.accuracy
