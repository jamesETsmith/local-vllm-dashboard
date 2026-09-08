import json
import shlex
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
    tensor_parallel_size: int | None
    server_settings_available: bool
    expert_parallel: bool
    speculative_decode: str | None
    decode_context_parallel_size: int | None
    kv_cache_offload: str | None
    configuration: dict[str, object]
    metrics: dict[str, float]


@dataclass(frozen=True)
class ModelChart:
    model: str
    points: tuple[ChartPoint, ...]


def serve_tokens(configuration: dict[str, object]) -> tuple[str, ...]:
    value = configuration.get("serve_args")
    if not isinstance(value, str):
        return ()
    try:
        return tuple(shlex.split(value))
    except ValueError:
        return tuple(value.split())


def flag_value(tokens: tuple[str, ...], flag: str) -> str | None:
    for index, token in enumerate(tokens):
        if token == flag and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith(f"{flag}="):
            return token.partition("=")[2]
    return None


def speculative_decode_label(tokens: tuple[str, ...]) -> str | None:
    config = flag_value(tokens, "--speculative-config")
    if config:
        try:
            parsed = json.loads(config)
        except json.JSONDecodeError:
            return config
        if isinstance(parsed, dict):
            preferred = ("method", "model", "num_speculative_tokens")
            values = [
                f"{key.replace('_', ' ')}: {parsed[key]}" for key in preferred if key in parsed
            ]
            return ", ".join(values) or config
    model = flag_value(tokens, "--speculative-model")
    count = flag_value(tokens, "--num-speculative-tokens")
    if model or count:
        return ", ".join(
            value
            for value in (
                f"model: {model}" if model else None,
                f"tokens: {count}" if count else None,
            )
            if value is not None
        )
    return None


def kv_cache_offload_label(tokens: tuple[str, ...]) -> str | None:
    size = flag_value(tokens, "--kv-offloading-size")
    backend = flag_value(tokens, "--kv-offloading-backend")
    if not size and not backend:
        return None
    return ", ".join(
        value
        for value in (
            f"size: {size}" if size else None,
            f"backend: {backend}" if backend else None,
        )
        if value is not None
    )


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
        server_settings_available = isinstance(row.configuration.get("serve_args"), str)
        tokens = serve_tokens(row.configuration)
        dcp = flag_value(tokens, "--decode-context-parallel-size")
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
                tensor_parallel_size=row.tensor_parallel_size,
                server_settings_available=server_settings_available,
                expert_parallel=row.expert_parallel,
                speculative_decode=speculative_decode_label(tokens),
                decode_context_parallel_size=(
                    int(dcp) if dcp and dcp.isdigit() else 1 if server_settings_available else None
                ),
                kv_cache_offload=kv_cache_offload_label(tokens),
                configuration=row.configuration,
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
