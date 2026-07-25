from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class DashboardFilters:
    hardware: str | None = None
    model: str | None = None
    workload: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    concurrency: int | None = None
    precision: str | None = None
    task: str | None = None


@dataclass(frozen=True)
class FilterOptions:
    hardware: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    workloads: tuple[str, ...] = ()
    input_tokens: tuple[int, ...] = ()
    output_tokens: tuple[int, ...] = ()
    concurrencies: tuple[int, ...] = ()
    precisions: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetricView:
    name: str
    value: float
    unit: str
    aggregation: str


@dataclass(frozen=True)
class PerformanceView:
    bundle_id: UUID
    completed_at: datetime
    hardware: str
    accelerator_count: int
    model: str
    workload: str
    precision: str | None
    input_tokens: int | None
    output_tokens: int | None
    concurrency: int | None
    completed_requests: int | None
    failed_requests: int | None
    metrics: tuple[MetricView, ...]


@dataclass(frozen=True)
class AccuracyView:
    bundle_id: UUID
    completed_at: datetime
    hardware: str
    model: str
    workload: str
    task: str
    fewshot: int
    partial: bool
    metrics: tuple[MetricView, ...]


@dataclass(frozen=True)
class RunView:
    bundle_id: UUID
    accepted_at: datetime
    completed_at: datetime
    workload: str
    model: str
    hardware: str
    accelerator_count: int
    vllm_image: str | None
    vllm_commit: str | None
    runner_kind: str
    observation_count: int
    artifact_count: int


@dataclass(frozen=True)
class DashboardData:
    performance: tuple[PerformanceView, ...] = ()
    accuracy: tuple[AccuracyView, ...] = ()
    runs: tuple[RunView, ...] = ()
    options: FilterOptions = field(default_factory=FilterOptions)
