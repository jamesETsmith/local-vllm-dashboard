from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class DashboardFilters:
    hardware: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    prefix_cache_tokens: int | None = None
    concurrency: int | None = None
    precision: str | None = None
    task: str | None = None


@dataclass(frozen=True)
class FilterOptions:
    hardware: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    input_tokens: tuple[int, ...] = ()
    output_tokens: tuple[int, ...] = ()
    prefix_cache_tokens: tuple[int, ...] = ()
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
    tensor_parallel_size: int | None
    data_parallel_size: int | None
    expert_parallel: bool
    input_tokens: int | None
    output_tokens: int | None
    prefix_cache_tokens: int | None
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
class RunDataRow:
    bundle_id: UUID
    completed_at: datetime
    hardware: str
    accelerator_count: int
    model: str
    precision: str | None
    tensor_parallel_size: int | None
    data_parallel_size: int | None
    expert_parallel: bool
    input_tokens: int | None
    output_tokens: int | None
    prefix_cache_tokens: int | None
    concurrency: int | None
    completed_requests: int | None
    failed_requests: int | None
    total_token_throughput_per_gpu: float | None
    output_token_throughput_per_gpu: float | None
    request_throughput_per_gpu: float | None
    mean_ttft: float | None
    p99_ttft: float | None
    mean_tpot: float | None
    p99_tpot: float | None
    mean_itl: float | None
    p99_itl: float | None
    mean_e2el: float | None
    p99_e2el: float | None
    vllm_image: str | None
    vllm_commit: str | None
    aiter_commit: str | None


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
    aiter_commit: str | None
    container: str | None
    runner_kind: str
    observation_count: int
    artifact_count: int


@dataclass(frozen=True)
class SourceArtifactView:
    path: str
    role: str
    title: str
    description: str
    media_type: str
    size_bytes: int
    digest: str
    text: str
    highlighted_html: str


@dataclass(frozen=True)
class RunDetailView:
    run: RunView
    reproduction_command: str | None
    reproduction_command_html: str | None
    payload_json: str
    payload_json_html: str
    configuration_json: tuple[str, ...]
    subject_json: tuple[str, ...]
    source_json: tuple[str, ...]
    metrics: tuple[tuple[MetricView, ...], ...]
    artifacts: tuple[SourceArtifactView, ...]


@dataclass(frozen=True)
class DashboardData:
    performance: tuple[PerformanceView, ...] = ()
    accuracy: tuple[AccuracyView, ...] = ()
    runs: tuple[RunView, ...] = ()
    run_data: tuple[RunDataRow, ...] = ()
    options: FilterOptions = field(default_factory=FilterOptions)
