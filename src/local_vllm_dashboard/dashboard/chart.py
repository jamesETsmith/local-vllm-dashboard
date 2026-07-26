from dataclasses import asdict, dataclass

from local_vllm_dashboard.dashboard.models import PerformanceView

THROUGHPUT_METRIC = "total_token_throughput_per_gpu"


@dataclass(frozen=True)
class ChartPoint:
    concurrency: int
    throughput: float
    completed_at: str
    bundle_id: str
    hardware: str
    model: str
    precision: str | None
    completed_requests: int | None
    failed_requests: int | None


@dataclass(frozen=True)
class ChartSeries:
    label: str
    points: tuple[ChartPoint, ...]


def workload_label(row: PerformanceView) -> str:
    input_tokens = row.input_tokens if row.input_tokens is not None else "?"
    output_tokens = row.output_tokens if row.output_tokens is not None else "?"
    prefix_tokens = row.prefix_cache_tokens if row.prefix_cache_tokens is not None else 0
    return f"ISL {input_tokens} · OSL {output_tokens} · Prefix {prefix_tokens}"


def performance_chart(rows: tuple[PerformanceView, ...]) -> tuple[ChartSeries, ...]:
    grouped: dict[str, list[ChartPoint]] = {}
    for row in rows:
        if row.concurrency is None:
            continue
        throughput = next(
            (metric.value for metric in row.metrics if metric.name == THROUGHPUT_METRIC),
            None,
        )
        if throughput is None:
            continue
        grouped.setdefault(workload_label(row), []).append(
            ChartPoint(
                concurrency=row.concurrency,
                throughput=throughput,
                completed_at=row.completed_at.isoformat(),
                bundle_id=str(row.bundle_id),
                hardware=row.hardware,
                model=row.model,
                precision=row.precision,
                completed_requests=row.completed_requests,
                failed_requests=row.failed_requests,
            )
        )
    return tuple(
        ChartSeries(
            label=label,
            points=tuple(sorted(points, key=lambda point: (point.concurrency, point.completed_at))),
        )
        for label, points in sorted(grouped.items())
    )


def chart_json_data(series: tuple[ChartSeries, ...]) -> tuple[dict[str, object], ...]:
    return tuple(asdict(trace) for trace in series)
