from datetime import UTC, datetime
from uuid import UUID

from local_vllm_dashboard.dashboard.chart import performance_chart
from local_vllm_dashboard.dashboard.models import MetricView, PerformanceView


def performance_row(concurrency: int, throughput: float, prefix: int) -> PerformanceView:
    return PerformanceView(
        bundle_id=UUID(int=concurrency),
        completed_at=datetime(2026, 7, concurrency, tzinfo=UTC),
        hardware="MI355X",
        accelerator_count=4,
        model="example/model",
        workload=f"attempt-{concurrency}",
        precision="mxfp4",
        input_tokens=50000,
        output_tokens=1000,
        prefix_cache_tokens=prefix,
        concurrency=concurrency,
        completed_requests=10,
        failed_requests=0,
        metrics=(
            MetricView(
                name="total_token_throughput_per_gpu",
                value=throughput,
                unit="token/s/gpu",
                aggregation="run",
            ),
        ),
    )


def test_chart_groups_by_token_and_prefix_configuration() -> None:
    chart = performance_chart(
        (
            performance_row(8, 100, 40000),
            performance_row(2, 50, 40000),
            performance_row(4, 75, 0),
        )
    )

    assert [series.label for series in chart] == [
        "ISL 50000 · OSL 1000 · Prefix 0",
        "ISL 50000 · OSL 1000 · Prefix 40000",
    ]
    assert [point.concurrency for point in chart[1].points] == [2, 8]
    assert chart[1].points[0].bundle_id == str(UUID(int=2))
    assert chart[1].points[0].model == "example/model"
