from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from local_vllm_dashboard.adapter import build_accuracy_bundle, build_performance_bundle
from local_vllm_dashboard.artifacts import artifact_contents
from local_vllm_dashboard.container_revisions import ContainerRevisions
from local_vllm_dashboard.dashboard.models import DashboardFilters
from local_vllm_dashboard.dashboard.repository import DashboardRepository, recipe_commands
from local_vllm_dashboard.db import Base, BundleRepository, make_engine, make_session_factory

FIXTURES = Path(__file__).parents[1] / "fixtures" / "perf_eval"


def dashboard_repository() -> DashboardRepository:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
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
    historical_observation = performance.observations[0].model_copy(
        update={
            "configuration": {
                key: value
                for key, value in performance.observations[0].configuration.items()
                if key not in {"args", "recipe_config", "serve_args"}
            }
        }
    )
    performance = performance.model_copy(update={"observations": (historical_observation,)})
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
    assert len(data.run_data) == 1
    assert data.run_data[0].hardware == "MI355X"
    assert data.run_data[0].tensor_parallel_size == 4
    assert data.run_data[0].total_token_throughput_per_gpu == 739.15939605178
    assert data.run_data[0].mean_ttft == 0.24936232599429786
    assert data.run_data[0].vllm_commit == "abcdef0"
    assert data.run_data[0].dependency_revisions == (("aiter", "fedcba0"),)
    assert cast(dict[str, Any], data.run_data[0].configuration["args"])["num_warmups"] == 32
    assert "--enable-prefix-caching" in cast(str, data.run_data[0].configuration["serve_args"])
    assert data.options.hardware == ("MI355X",)
    assert data.options.tasks == ("gsm8k",)
    assert data.options.prefix_cache_tokens == (40000,)
    assert data.performance[0].failed_requests == 39
    configuration = data.performance[0].configuration
    assert cast(dict[str, Any], configuration["args"])["num_warmups"] == 32
    assert "--enable-prefix-caching" in cast(str, configuration["serve_args"])
    assert configuration["expert_parallel"] is False
    assert data.accuracy[0].fewshot == 5


def test_recipe_commands_translate_perf_eval_configuration() -> None:
    recipe = {
        "gpu": "MI355X",
        "num_gpus": 4,
        "vllm": {
            "model": "example-org/example-model",
            "image": "example-registry/vllm-openai:test",
            "env": {
                "VLLM_ROCM_USE_AITER": 1,
                "FEATURE_ENABLED": True,
                "HF_HOME": "/models/huggingface cache",
            },
            "serve_args": "--tensor-parallel-size 4 --trust-remote-code",
        },
    }
    configuration = {
        "backend": "openai",
        "dataset": "random",
        "input_tokens": 1024,
        "output_tokens": 512,
        "num_prompts": 32,
        "max_concurrency": 8,
        "args": {
            "num_warmups": 8,
            "disable_tqdm": True,
            "profile": False,
            "request_rate": None,
            "custom": ["one", "two"],
        },
    }

    commands = recipe_commands(recipe, configuration)

    assert commands is not None
    assert commands.server == (
        "docker run --rm --device=/dev/kfd --device=/dev/dri --security-opt seccomp=unconfined "
        "--group-add video --privileged --ipc=host --ulimit nofile=65536:65536 \\\n"
        "  -p 8000:8000 \\\n"
        "  -e VLLM_ENGINE_READY_TIMEOUT_S=3600 \\\n"
        "  -e VLLM_ROCM_USE_AITER=1 \\\n"
        "  -e FEATURE_ENABLED=true \\\n"
        "  -e 'HF_HOME=/models/huggingface cache' \\\n"
        "  -v '/models/huggingface cache:/models/huggingface cache' \\\n"
        "  example-registry/vllm-openai:test \\\n"
        "  example-org/example-model \\\n"
        "  --port 8000 \\\n"
        "  --tensor-parallel-size 4 \\\n"
        "  --trust-remote-code"
    )
    assert commands.benchmark == (
        "vllm bench serve \\\n"
        "  --backend openai \\\n"
        "  --base-url http://127.0.0.1:8000 \\\n"
        "  --model example-org/example-model \\\n"
        "  --dataset-name random \\\n"
        "  --num-prompts 32 \\\n"
        "  --max-concurrency 8 \\\n"
        "  --trust-remote-code \\\n"
        "  --random-input-len 1024 \\\n"
        "  --random-output-len 512 \\\n"
        "  --ignore-eos \\\n"
        "  --num-warmups 8 \\\n"
        "  --disable-tqdm \\\n"
        "  --custom one \\\n"
        "  --custom two"
    )


def test_recipe_commands_translate_cuda_configuration() -> None:
    commands = recipe_commands(
        {
            "gpu": "H200",
            "vllm": {
                "model": "example-org/model",
                "image": "vllm/vllm-openai:nightly",
            },
        },
        {
            "dataset": "random",
            "input_tokens": 16,
            "output_tokens": 8,
            "num_prompts": 4,
            "max_concurrency": 2,
        },
    )

    assert commands is not None
    assert commands.server.startswith("docker run --rm --gpus all")
    assert "--device=/dev/kfd" not in commands.server
    assert "--host 127.0.0.1" in commands.benchmark
    assert "--port 8000" in commands.benchmark


def test_recipe_commands_reject_incomplete_recipes() -> None:
    configuration = {
        "dataset": "prefix_repetition",
        "num_prompts": 32,
        "max_concurrency": 8,
    }

    assert recipe_commands({}, configuration) is None
    assert recipe_commands({"vllm": {"model": "model"}}, configuration) is None
    assert (
        recipe_commands(
            {"vllm": {"model": "model", "image": "image", "runtime": "native"}},
            configuration,
        )
        is None
    )


def test_repository_loads_full_run_detail() -> None:
    repository = dashboard_repository()
    bundle_id = repository.load().performance[0].bundle_id

    detail = repository.detail(bundle_id)

    assert detail is not None
    assert detail.run.bundle_id == bundle_id
    assert detail.run.dependency_revisions == (("aiter", "fedcba0"),)
    assert len(detail.recipes) == 1
    assert "docker run --rm --device=/dev/kfd" in detail.recipes[0].server
    assert "example-registry/vllm-openai:test" in detail.recipes[0].server
    assert "--enable-prefix-caching" in detail.recipes[0].server
    assert "vllm bench serve" in detail.recipes[0].benchmark
    assert "--dataset-name prefix_repetition" in detail.recipes[0].benchmark
    assert "--prefix-repetition-prefix-len 40000" in detail.recipes[0].benchmark
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
        DashboardFilters(hardware=("MI355X",), concurrency=(4,), prefix_cache_tokens=(40000,))
    )
    matching_multiple = repository.load(
        DashboardFilters(hardware=("H200", "MI355X"), concurrency=(4, 8))
    )
    missing = repository.load(DashboardFilters(hardware=("H200",)))

    assert len(matching.performance) == 1
    assert len(matching_multiple.performance) == 1
    assert not missing.performance
    assert not missing.accuracy
    assert not missing.runs
    assert matching.options.hardware == ("MI355X",)
    assert not repository.load(DashboardFilters(prefix_cache_tokens=(0,))).performance


def test_repository_filters_accuracy_task() -> None:
    repository = dashboard_repository()

    matching = repository.load(DashboardFilters(task=("gsm8k", "aime25")))
    missing = repository.load(DashboardFilters(task=("aime25",)))

    assert len(matching.accuracy) == 1
    assert not missing.accuracy


def test_repository_filters_all_views_by_inclusive_completion_dates() -> None:
    repository = dashboard_repository()
    unfiltered = repository.load()
    performance_date = unfiltered.performance[0].completed_at.date()
    accuracy_date = unfiltered.accuracy[0].completed_at.date()

    performance_only = repository.load(
        DashboardFilters(start_date=performance_date, end_date=performance_date)
    )
    accuracy_only = repository.load(
        DashboardFilters(start_date=accuracy_date, end_date=accuracy_date)
    )
    after_all_results = repository.load(DashboardFilters(start_date=date(2099, 1, 1)))
    before_all_results = repository.load(DashboardFilters(end_date=date(2000, 1, 1)))

    assert len(performance_only.performance) == 1
    assert not performance_only.accuracy
    assert len(performance_only.runs) == 1
    assert len(performance_only.run_data) == 1
    assert not accuracy_only.performance
    assert len(accuracy_only.accuracy) == 1
    assert len(accuracy_only.runs) == 1
    assert not accuracy_only.run_data
    assert not after_all_results.performance
    assert not after_all_results.accuracy
    assert not after_all_results.runs
    assert not before_all_results.performance
    assert not before_all_results.accuracy
    assert not before_all_results.runs
