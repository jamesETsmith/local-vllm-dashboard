from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import yaml

from local_vllm_dashboard import __version__
from local_vllm_dashboard.contracts import (
    ArtifactRole,
    Bundle,
    Environment,
    Metric,
    MetricAggregation,
    MetricName,
    Observation,
    ObservationKind,
    ObservationSource,
    RawArtifactProvenance,
    Run,
    Runner,
    Source,
    Vllm,
    Workload,
)

LATENCY_METRICS = {
    "mean_ttft_ms": (MetricName.MEAN_TTFT, MetricAggregation.MEAN),
    "median_ttft_ms": (MetricName.MEDIAN_TTFT, MetricAggregation.MEDIAN),
    "p99_ttft_ms": (MetricName.P99_TTFT, MetricAggregation.P99),
    "mean_tpot_ms": (MetricName.MEAN_TPOT, MetricAggregation.MEAN),
    "median_tpot_ms": (MetricName.MEDIAN_TPOT, MetricAggregation.MEDIAN),
    "p99_tpot_ms": (MetricName.P99_TPOT, MetricAggregation.P99),
    "mean_itl_ms": (MetricName.MEAN_ITL, MetricAggregation.MEAN),
    "median_itl_ms": (MetricName.MEDIAN_ITL, MetricAggregation.MEDIAN),
    "p99_itl_ms": (MetricName.P99_ITL, MetricAggregation.P99),
    "mean_e2el_ms": (MetricName.MEAN_E2EL, MetricAggregation.MEAN),
    "median_e2el_ms": (MetricName.MEDIAN_E2EL, MetricAggregation.MEDIAN),
    "p99_e2el_ms": (MetricName.P99_E2EL, MetricAggregation.P99),
}
THROUGHPUT_METRICS = {
    "request_throughput": MetricName.REQUEST_THROUGHPUT_PER_GPU,
    "output_throughput": MetricName.OUTPUT_TOKEN_THROUGHPUT_PER_GPU,
    "total_token_throughput": MetricName.TOTAL_TOKEN_THROUGHPUT_PER_GPU,
}


def file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def parse_result_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d-%H%M%S").replace(tzinfo=UTC)


def load_mapping(path: Path) -> dict[str, Any]:
    if path.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(path.read_text())
    else:
        data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"expected an object in {path}")
    return data


def find_bench_config(recipe: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    configs = recipe.get("vllm_bench", {}).get("configs", [])
    concurrency = result.get("max_concurrency")
    prompts = result.get("num_prompts")
    matches = [
        config
        for config in configs
        if config.get("max_concurrency") == concurrency and config.get("num_prompts") == prompts
    ]
    if len(matches) != 1:
        raise ValueError("could not identify exactly one matching vllm_bench config")
    return matches[0]


def performance_metrics(result: dict[str, Any], parallelism: int) -> tuple[Metric, ...]:
    if parallelism < 1:
        raise ValueError("throughput parallelism must be positive")
    metrics = [
        Metric(
            name=name,
            value=float(result[field]) / parallelism,
            unit="request/s/gpu" if field == "request_throughput" else "token/s/gpu",
            aggregation=MetricAggregation.RUN,
        )
        for field, name in THROUGHPUT_METRICS.items()
        if result.get(field) is not None
    ]
    metrics.extend(
        Metric(name=name, value=float(result[field]) / 1000, unit="s", aggregation=aggregation)
        for field, (name, aggregation) in LATENCY_METRICS.items()
        if result.get(field) is not None
    )
    return tuple(metrics)


def build_performance_bundle(
    recipe_path: Path,
    result_path: Path,
    *,
    bundle_id: UUID | None = None,
    runner: Runner | None = None,
    source_revision: str | None = None,
) -> Bundle:
    recipe = load_mapping(recipe_path)
    result = load_mapping(result_path)
    config = find_bench_config(recipe, result)
    vllm = recipe["vllm"]
    bench_metadata = recipe.get("vllm_bench", {}).get("metadata", {})
    parallelism = int(bench_metadata["tp"])
    completed_at = parse_result_time(str(result["date"]))
    duration = float(result.get("duration") or 0)
    selected_bundle_id = bundle_id or uuid4()

    bundle = Bundle(
        schema_version="v1",
        bundle_id=selected_bundle_id,
        idempotency_key=f"sha256:{'0' * 64}",
        run=Run(
            started_at=completed_at - timedelta(seconds=duration),
            completed_at=completed_at,
            status="completed",
            runner=runner or Runner(kind="local"),
            source=Source(
                kind="perf-eval",
                revision=source_revision,
                artifacts=(
                    RawArtifactProvenance(
                        path=recipe_path.name,
                        role=ArtifactRole.WORKLOAD_RECIPE,
                        size_bytes=recipe_path.stat().st_size,
                        digest=file_digest(recipe_path),
                    ),
                    RawArtifactProvenance(
                        path=result_path.name,
                        role=ArtifactRole.RAW_BENCH_RESULT,
                        size_bytes=result_path.stat().st_size,
                        digest=file_digest(result_path),
                    ),
                ),
            ),
            vllm=Vllm(image=str(vllm["image"])),
        ),
        workload=Workload(
            name=str(recipe["name"]),
            recipe_digest=file_digest(recipe_path),
            model=str(vllm["model"]),
            reference=recipe_path.name,
        ),
        environment=Environment(
            accelerator=str(recipe["gpu"]),
            accelerator_count=int(recipe["num_gpus"]),
            precision=str(bench_metadata["precision"]) if bench_metadata.get("precision") else None,
            tensor_parallel_size=parallelism,
        ),
        observations=(
            Observation(
                observation_id=f"bench:{config['name']}",
                kind=ObservationKind.PERFORMANCE,
                subject={"model": str(result.get("model_id") or vllm["model"])},
                configuration={
                    "name": str(config["name"]),
                    "backend": str(config["backend"]),
                    "dataset": str(config["dataset"]),
                    "input_tokens": int(config["input_len"]),
                    "output_tokens": int(config["output_len"]),
                    "num_prompts": int(config["num_prompts"]),
                    "max_concurrency": int(config["max_concurrency"]),
                    "completed": int(result["completed"]),
                    "failed": int(result["failed"]),
                },
                metrics=performance_metrics(result, parallelism),
                source=ObservationSource(adapter="perf-eval", adapter_version=__version__),
            ),
        ),
    )
    return bundle.model_copy(update={"idempotency_key": bundle.calculated_idempotency_key()})
