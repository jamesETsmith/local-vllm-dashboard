from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from local_vllm_dashboard.adapter import build_accuracy_bundle
from local_vllm_dashboard.contracts import MetricName

FIXTURES = Path(__file__).parents[1] / "fixtures" / "perf_eval"


def test_build_accuracy_bundle() -> None:
    bundle = build_accuracy_bundle(
        FIXTURES / "prefix_cache_workload.yaml",
        FIXTURES / "lm_eval_results.json",
        task="gsm8k",
        bundle_id=UUID("018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1d"),
        completed_at=datetime(2026, 7, 23, tzinfo=UTC),
    )

    assert bundle.has_valid_idempotency_key()
    assert bundle.observations[0].configuration["num_fewshot"] == 5
    metrics = {metric.name: metric for metric in bundle.observations[0].metrics}
    assert metrics[MetricName.EXACT_MATCH].value == 0.742
    assert metrics[MetricName.STANDARD_ERROR].value == 0.012


def test_accuracy_bundle_reduces_local_model_path_to_repository_identifier(tmp_path: Path) -> None:
    recipe = FIXTURES / "prefix_cache_workload.yaml"
    recipe_text = recipe.read_text().replace(
        "model: example-org/example-model",
        "model: /models/nvidia/Kimi-K3-NVFP4",
    )
    local_model_recipe = tmp_path / "local_model_workload.yaml"
    local_model_recipe.write_text(recipe_text)

    bundle = build_accuracy_bundle(
        local_model_recipe,
        FIXTURES / "lm_eval_results.json",
        task="gsm8k",
        bundle_id=UUID("018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1d"),
        completed_at=datetime(2026, 7, 23, tzinfo=UTC),
    )

    assert bundle.workload.model == "nvidia/Kimi-K3-NVFP4"
    assert bundle.observations[0].subject["model"] == "nvidia/Kimi-K3-NVFP4"
