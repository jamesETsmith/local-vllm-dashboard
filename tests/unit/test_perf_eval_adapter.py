from pathlib import Path
from uuid import UUID

from local_vllm_dashboard.adapter import build_performance_bundle
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
    assert bundle.observations[0].configuration["completed"] == 1
    assert bundle.observations[0].configuration["failed"] == 39
    metrics = {metric.name: metric for metric in bundle.observations[0].metrics}
    assert metrics[MetricName.MEAN_TTFT].value == 0.24936232599429786
    assert metrics[MetricName.TOTAL_TOKEN_THROUGHPUT].value == 2956.63758420712


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
