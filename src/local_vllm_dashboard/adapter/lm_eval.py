from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from local_vllm_dashboard import __version__
from local_vllm_dashboard.adapter.perf_eval import file_digest, load_mapping
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

ACCURACY_NAMES = {
    "acc": MetricName.ACCURACY,
    "acc_norm": MetricName.ACCURACY_NORMALIZED,
    "exact_match": MetricName.EXACT_MATCH,
}


def task_metrics(task_result: dict[str, Any]) -> tuple[Metric, ...]:
    metrics = []
    for source_name, canonical_name in ACCURACY_NAMES.items():
        if source_name in task_result:
            metrics.append(
                Metric(
                    name=canonical_name,
                    value=float(task_result[source_name]),
                    unit="1",
                    aggregation=MetricAggregation.MEAN,
                )
            )
        standard_error_name = f"{source_name}_stderr"
        if standard_error_name in task_result:
            metrics.append(
                Metric(
                    name=MetricName.STANDARD_ERROR,
                    value=float(task_result[standard_error_name]),
                    unit="1",
                    aggregation=MetricAggregation.STANDARD_ERROR,
                )
            )
    if not metrics:
        raise ValueError("lm-eval task has no supported metrics")
    return tuple(metrics)


def build_accuracy_bundle(
    recipe_path: Path,
    result_path: Path,
    *,
    task: str,
    bundle_id: UUID | None = None,
    runner: Runner | None = None,
    completed_at: datetime | None = None,
    source_revision: str | None = None,
) -> Bundle:
    recipe = load_mapping(recipe_path)
    result = load_mapping(result_path)
    task_result = result.get("results", {}).get(task)
    if not isinstance(task_result, dict):
        raise ValueError(f"lm-eval result does not contain task {task}")
    task_config = result.get("configs", {}).get(task, {})
    vllm = recipe["vllm"]
    timestamp = completed_at or datetime.fromtimestamp(result_path.stat().st_mtime, tz=UTC)
    bundle = Bundle(
        schema_version="v1",
        bundle_id=bundle_id or uuid4(),
        idempotency_key=f"sha256:{'0' * 64}",
        run=Run(
            started_at=timestamp,
            completed_at=timestamp,
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
                        role=ArtifactRole.ACCURACY_RESULT,
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
        ),
        observations=(
            Observation(
                observation_id=f"lm-eval:{task}",
                kind=ObservationKind.ACCURACY,
                subject={"model": str(vllm["model"]), "task": task},
                configuration={
                    "num_fewshot": int(task_config.get("num_fewshot", 0)),
                    "partial": False,
                },
                metrics=task_metrics(task_result),
                source=ObservationSource(adapter="perf-eval", adapter_version=__version__),
            ),
        ),
    )
    return bundle.model_copy(update={"idempotency_key": bundle.calculated_idempotency_key()})
