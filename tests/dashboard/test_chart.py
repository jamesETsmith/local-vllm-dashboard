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
) -> PerformanceView:
    return PerformanceView(
        bundle_id=UUID(int=concurrency),
        completed_at=datetime(2026, 7, concurrency, tzinfo=UTC),
        hardware=hardware,
        accelerator_count=4,
        model=model,
        workload=f"attempt-{concurrency}",
        precision="mxfp4",
        tensor_parallel_size=4,
        data_parallel_size=1,
        expert_parallel=False,
        input_tokens=50000,
        output_tokens=1000,
        prefix_cache_tokens=prefix,
        concurrency=concurrency,
        completed_requests=10,
        failed_requests=0,
        configuration={"expert_parallel": False},
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
    assert chart[0].points[1].configuration == {"expert_parallel": False}
    assert chart[0].points[1].metrics == {
        "total_token_throughput_per_gpu": 50,
        "output_token_throughput_per_gpu": 25,
        "mean_ttft": 0.1,
        "mean_tpot": 0.02,
    }
