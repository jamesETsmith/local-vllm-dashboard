from dataclasses import asdict, dataclass

from local_vllm_dashboard.dashboard.models import PerformanceView

CHART_METRICS = (
    "total_token_throughput_per_gpu",
    "output_token_throughput_per_gpu",
    "mean_ttft",
    "mean_tpot",
)


@dataclass(frozen=True)
class ChartPoint:
    concurrency: int
    input_tokens: int | None
    output_tokens: int | None
    prefix_cache_tokens: int | None
    completed_at: str
    bundle_id: str
    hardware: str
    precision: str | None
    completed_requests: int | None
    failed_requests: int | None
    metrics: dict[str, float]


@dataclass(frozen=True)
class ModelChart:
    model: str
    points: tuple[ChartPoint, ...]


def performance_chart(rows: tuple[PerformanceView, ...]) -> tuple[ModelChart, ...]:
    grouped: dict[str, list[ChartPoint]] = {}
    for row in rows:
        if row.concurrency is None:
            continue
        metrics = {
            metric.name: metric.value for metric in row.metrics if metric.name in CHART_METRICS
        }
        if not metrics:
            continue
        grouped.setdefault(row.model, []).append(
            ChartPoint(
                concurrency=row.concurrency,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                prefix_cache_tokens=row.prefix_cache_tokens,
                completed_at=row.completed_at.isoformat(),
                bundle_id=str(row.bundle_id),
                hardware=row.hardware,
                precision=row.precision,
                completed_requests=row.completed_requests,
                failed_requests=row.failed_requests,
                metrics=metrics,
            )
        )
    return tuple(
        ModelChart(
            model=model,
            points=tuple(
                sorted(
                    points,
                    key=lambda point: (
                        point.input_tokens or 0,
                        point.output_tokens or 0,
                        point.prefix_cache_tokens or 0,
                        point.concurrency,
                        point.hardware,
                        point.completed_at,
                    ),
                )
            ),
        )
        for model, points in sorted(grouped.items())
    )


def chart_json_data(charts: tuple[ModelChart, ...]) -> tuple[dict[str, object], ...]:
    return tuple(asdict(chart) for chart in charts)
