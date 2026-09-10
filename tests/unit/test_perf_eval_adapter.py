from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from local_vllm_dashboard.adapter import build_performance_bundle
from local_vllm_dashboard.adapter.perf_eval import model_identifier
from local_vllm_dashboard.container_revisions import ContainerRevisions
from local_vllm_dashboard.contracts import MetricName

FIXTURES = Path(__file__).parents[1] / "fixtures" / "perf_eval"


def test_build_performance_bundle_from_real_shape() -> None:
    bundle = build_performance_bundle(
        FIXTURES / "prefix_cache_workload.yaml",
        FIXTURES / "prefix_cache_partial_failure_bench.json",
        bundle_id=UUID("018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1c"),
    )

    assert bundle.has_valid_idempotency_key()
    assert bundle.workload.name == "prefix-cache-performance-mi355x"
    assert bundle.environment.accelerator == "MI355X"
    assert bundle.environment.tensor_parallel_size == 4
    assert bundle.environment.data_parallel_size == 1
    assert bundle.environment.extensions.get("expert_parallel") is False
    assert bundle.observations[0].configuration["completed"] == 1
    assert bundle.observations[0].configuration["failed"] == 39
    assert bundle.observations[0].configuration["prefix_cache_tokens"] == 40000
    assert bundle.observations[0].configuration["args"] == {
        "num_warmups": 32,
        "percentile_metrics": "ttft,tpot,itl,e2el",
        "prefix_repetition_num_prefixes": 1,
        "prefix_repetition_prefix_len": 40000,
        "prefix_repetition_suffix_len": 10000,
        "prefix_repetition_output_len": 1000,
        "disable_tqdm": True,
    }
    assert "--enable-prefix-caching" in cast(
        str, bundle.observations[0].configuration["serve_args"]
    )
    metrics = {metric.name: metric for metric in bundle.observations[0].metrics}
    assert metrics[MetricName.MEAN_TTFT].value == 0.24936232599429786
    total = metrics[MetricName.TOTAL_TOKEN_THROUGHPUT_PER_GPU]
    requests = metrics[MetricName.REQUEST_THROUGHPUT_PER_GPU]
    assert total.value == 739.15939605178
    assert total.unit == "token/s/gpu"
    assert requests.value == 0.014782596617170914
    assert requests.unit == "request/s/gpu"


@pytest.mark.parametrize(
    ("configured_model", "expected_model"),
    [
        ("nvidia/Kimi-K3-NVFP4", "nvidia/Kimi-K3-NVFP4"),
        ("/models/nvidia/Kimi-K3-NVFP4", "nvidia/Kimi-K3-NVFP4"),
        (
            "/root/.cache/huggingface/hub/models--nvidia--Kimi-K3-NVFP4/snapshots/abc123",
            "nvidia/Kimi-K3-NVFP4",
        ),
    ],
)
def test_model_identifier_extracts_repository_name_from_local_path(
    configured_model: str,
    expected_model: str,
) -> None:
    assert model_identifier(configured_model) == expected_model


def test_performance_bundle_uses_model_extracted_from_local_path(tmp_path: Path) -> None:
    recipe = FIXTURES / "prefix_cache_workload.yaml"
    recipe_text = recipe.read_text().replace(
        "model: example-org/example-model",
        "model: /models/nvidia/Kimi-K3-NVFP4",
    )
    local_model_recipe = tmp_path / "local_model_workload.yaml"
    local_model_recipe.write_text(recipe_text)

    bundle = build_performance_bundle(
        local_model_recipe,
        FIXTURES / "prefix_cache_partial_failure_bench.json",
        bundle_id=UUID("018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1c"),
    )

    assert bundle.workload.model == "nvidia/Kimi-K3-NVFP4"
    assert bundle.observations[0].subject["model"] == "nvidia/Kimi-K3-NVFP4"


def test_performance_bundle_resolves_sweep_to_scalar_configuration(tmp_path: Path) -> None:
    recipe = FIXTURES / "prefix_cache_workload.yaml"
    recipe_text = recipe.read_text().replace(
        "num_prompts: 40\n      max_concurrency: 4",
        "num_prompts: [10, 40]\n      max_concurrency: [1, 4]",
    )
    sweep_recipe = tmp_path / "sweep_workload.yaml"
    sweep_recipe.write_text(recipe_text)

    bundle = build_performance_bundle(
        sweep_recipe,
        FIXTURES / "prefix_cache_partial_failure_bench.json",
        bundle_id=UUID("018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1c"),
    )

    configuration = bundle.observations[0].configuration
    recipe_config = cast(dict, configuration["recipe_config"])
    assert configuration["num_prompts"] == 40
    assert configuration["max_concurrency"] == 4
    assert recipe_config["num_prompts"] == 40
    assert recipe_config["max_concurrency"] == 4


def test_random_prefix_is_included_in_total_input_tokens(tmp_path: Path) -> None:
    recipe = FIXTURES / "prefix_cache_workload.yaml"
    recipe_text = (
        recipe.read_text()
        .replace(
            "dataset: prefix_repetition\n      input_len: 50000",
            "dataset: random\n      input_len: 10000",
        )
        .replace(
            "prefix_repetition_prefix_len: 40000",
            "random_prefix_len: 40000",
        )
    )
    random_prefix_recipe = tmp_path / "random_prefix_workload.yaml"
    random_prefix_recipe.write_text(recipe_text)

    bundle = build_performance_bundle(
        random_prefix_recipe,
        FIXTURES / "prefix_cache_partial_failure_bench.json",
        bundle_id=UUID("018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1c"),
    )

    configuration = bundle.observations[0].configuration
    assert configuration["input_tokens"] == 50000
    assert configuration["prefix_cache_tokens"] == 40000


def test_top_level_random_prefix_preserves_total_input_tokens(tmp_path: Path) -> None:
    recipe = FIXTURES / "prefix_cache_workload.yaml"
    recipe_text = (
        recipe.read_text()
        .replace(
            "dataset: prefix_repetition\n      input_len: 50000",
            "dataset: random\n      input_len: 50000\n      prefix_len: 40000",
        )
        .replace("        prefix_repetition_prefix_len: 40000\n", "")
    )
    random_prefix_recipe = tmp_path / "top_level_random_prefix_workload.yaml"
    random_prefix_recipe.write_text(recipe_text)

    bundle = build_performance_bundle(
        random_prefix_recipe,
        FIXTURES / "prefix_cache_partial_failure_bench.json",
        bundle_id=UUID("018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1c"),
    )

    configuration = bundle.observations[0].configuration
    assert configuration["input_tokens"] == 50000
    assert configuration["prefix_cache_tokens"] == 40000


def test_bundle_includes_container_revisions_when_provided() -> None:
    bundle = build_performance_bundle(
        FIXTURES / "prefix_cache_workload.yaml",
        FIXTURES / "prefix_cache_partial_failure_bench.json",
        bundle_id=UUID("018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1c"),
        container_revisions=ContainerRevisions(
            container="perf-eval-demo-123",
            vllm_commit="abcdef0",
            aiter_commit="fedcba0",
        ),
    )

    assert bundle.run.vllm.commit == "abcdef0"
    assert bundle.environment.extensions.get("aiter_commit") == "fedcba0"
    assert bundle.run.source.extensions.get("container") == "perf-eval-demo-123"


def test_bundle_generation_is_deterministic_for_fixed_bundle_id() -> None:
    bundle_id = UUID("018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1c")
    first = build_performance_bundle(
        FIXTURES / "prefix_cache_workload.yaml",
        FIXTURES / "prefix_cache_partial_failure_bench.json",
        bundle_id=bundle_id,
    )
    second = build_performance_bundle(
        FIXTURES / "prefix_cache_workload.yaml",
        FIXTURES / "prefix_cache_partial_failure_bench.json",
        bundle_id=bundle_id,
    )

    assert first == second
