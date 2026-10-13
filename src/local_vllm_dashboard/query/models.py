from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class QueryModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MetricResult(QueryModel):
    name: str
    value: float
    unit: str
    aggregation: str


class ConfigurationResult(QueryModel):
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
    metrics: tuple[MetricResult, ...]


class ConfigurationFilters(QueryModel):
    hardware: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    prefix_cache_tokens: int | None = None
    concurrency: int | None = None
    precision: str | None = None


class ConfigurationPage(QueryModel):
    items: tuple[ConfigurationResult, ...]
    total: int
    limit: int
    offset: int


class ConfigurationFilterOptions(QueryModel):
    hardware: tuple[str, ...]
    models: tuple[str, ...]
    input_tokens: tuple[int, ...]
    output_tokens: tuple[int, ...]
    prefix_cache_tokens: tuple[int, ...]
    concurrencies: tuple[int, ...]
    precisions: tuple[str, ...]


class ReproductionArtifact(QueryModel):
    path: str
    role: str
    media_type: str
    size_bytes: int
    digest: str
    content: str


class ReproductionRun(QueryModel):
    bundle_id: UUID
    workload: str
    model: str
    hardware: str
    completed_at: datetime
    vllm_image: str | None
    vllm_commit: str | None
    dependency_revisions: tuple[tuple[str, str], ...] = ()


class ReproductionRecipe(QueryModel):
    observation_id: str
    server_command: str
    benchmark_command: str


class ReproductionResult(QueryModel):
    run: ReproductionRun
    perf_eval_command: str | None
    recipes: tuple[ReproductionRecipe, ...] = ()
    artifacts: tuple[ReproductionArtifact, ...] = ()


PageLimit = Annotated[int, Field(ge=1, le=100)]
PageOffset = Annotated[int, Field(ge=0)]
