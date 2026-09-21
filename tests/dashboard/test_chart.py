from datetime import UTC, datetime
from uuid import UUID

from local_vllm_dashboard.dashboard.chart import performance_chart
from local_vllm_dashboard.dashboard.models import MetricView, PerformanceView


def performance_row(
    concurrency: int,
    throughput: float,
    prefix: int,
    hardware: str = "MI355X",
    model: str = "example/model",
    tensor_parallel_size: int | None = 4,
    configuration: dict[str, object] | None = None,
) -> PerformanceView:
    return PerformanceView(
        bundle_id=UUID(int=concurrency),
        completed_at=datetime(2026, 7, concurrency, tzinfo=UTC),
        hardware=hardware,
        accelerator_count=4,
        model=model,
        workload=f"attempt-{concurrency}",
        precision="mxfp4",
        tensor_parallel_size=tensor_parallel_size,
        data_parallel_size=1,
        expert_parallel=False,
        input_tokens=50000,
        output_tokens=1000,
        prefix_cache_tokens=prefix,
        concurrency=concurrency,
        completed_requests=10,
        failed_requests=0,
        configuration=(
            configuration
            if configuration is not None
            else {
                "expert_parallel": False,
                "serve_args": (
                    "--tensor-parallel-size 4 --decode-context-parallel-size 8 "
                    "--speculative-config "
                    '\'{"method":"dspark","model":"example/draft",'
                    '"num_speculative_tokens":7}\' '
                    "--kv-offloading-size 32 --kv-offloading-backend native"
                ),
            }
        ),
        metrics=(
            MetricView(
                name="total_token_throughput_per_gpu",
                value=throughput,
                unit="token/s/gpu",
                aggregation="run",
            ),
            MetricView(
                name="output_token_throughput_per_gpu",
                value=throughput / 2,
                unit="token/s/gpu",
                aggregation="run",
            ),
            MetricView(name="mean_ttft", value=0.1, unit="s", aggregation="mean"),
            MetricView(name="mean_tpot", value=0.02, unit="s", aggregation="mean"),
            MetricView(name="median_e2el", value=25.0, unit="s", aggregation="median"),
            MetricView(name="p99_e2el", value=40.0, unit="s", aggregation="p99"),
        ),
    )


def test_chart_groups_all_metrics_by_model() -> None:
    chart = performance_chart(
        (
            performance_row(8, 100, 40000),
            performance_row(2, 50, 40000),
            performance_row(4, 75, 0),
            performance_row(4, 120, 40000, "B300"),
            performance_row(2, 90, 0, model="other/model"),
        )
    )

    assert [model_chart.model for model_chart in chart] == ["example/model", "other/model"]
    assert [point.concurrency for point in chart[0].points] == [4, 2, 4, 8]
    assert chart[0].points[1].bundle_id == str(UUID(int=2))
    assert chart[0].points[1].hardware == "MI355X"
    assert chart[0].points[1].configuration["expert_parallel"] is False
    assert chart[0].points[1].tensor_parallel_size == 4
    assert chart[0].points[1].expert_parallel is False
    assert chart[0].points[1].speculative_decode == (
        "method: dspark, model: example/draft, num speculative tokens: 7"
    )
    assert chart[0].points[1].decode_context_parallel_size == 8
    assert chart[0].points[1].kv_cache_offload == "size: 32, backend: native"
    assert chart[0].points[1].metrics == {
        "total_token_throughput_per_gpu": 50,
        "output_token_throughput_per_gpu": 25,
        "mean_ttft": 0.1,
        "mean_tpot": 0.02,
        "median_e2el": 25.0,
        "p99_e2el": 40.0,
    }


def test_chart_preserves_unavailable_server_settings() -> None:
    chart = performance_chart(
        (performance_row(2, 50, 0, tensor_parallel_size=None, configuration={}),)
    )

    point = chart[0].points[0]
    assert point.tensor_parallel_size is None
    assert point.server_settings_available is False
    assert point.decode_context_parallel_size is None
