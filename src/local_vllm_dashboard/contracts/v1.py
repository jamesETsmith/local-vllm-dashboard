from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ObservationKind(StrEnum):
    PERFORMANCE = "performance"
    ACCURACY = "accuracy"
    FUNCTION_CALLING = "function_calling"


class MetricName(StrEnum):
    REQUEST_THROUGHPUT = "request_throughput"
    INPUT_TOKEN_THROUGHPUT = "input_token_throughput"
    OUTPUT_TOKEN_THROUGHPUT = "output_token_throughput"
    TOTAL_TOKEN_THROUGHPUT = "total_token_throughput"
    MEAN_TTFT = "mean_ttft"
    MEDIAN_TTFT = "median_ttft"
    P99_TTFT = "p99_ttft"
    MEAN_TPOT = "mean_tpot"
    MEDIAN_TPOT = "median_tpot"
    P99_TPOT = "p99_tpot"
    MEAN_ITL = "mean_itl"
    MEDIAN_ITL = "median_itl"
    P99_ITL = "p99_itl"
    MEAN_E2EL = "mean_e2el"
    MEDIAN_E2EL = "median_e2el"
    P99_E2EL = "p99_e2el"
    ACCURACY = "accuracy"
    EXACT_MATCH = "exact_match"
    ACCURACY_NORMALIZED = "accuracy_normalized"
    STANDARD_ERROR = "standard_error"


class MetricAggregation(StrEnum):
    RUN = "run"
    MEAN = "mean"
    MEDIAN = "median"
    P99 = "p99"
    STANDARD_ERROR = "standard_error"


class ArtifactRole(StrEnum):
    RAW_BENCH_RESULT = "raw_bench_result"
    ACCURACY_RESULT = "accuracy_result"
    ACCURACY_SAMPLES = "accuracy_samples"
    FUNCTION_CALLING_RESULT = "function_calling_result"
    WORKLOAD_RECIPE = "workload_recipe"


class Runner(ContractModel):
    kind: NonEmptyString
    run_id: NonEmptyString | None = None
    url: NonEmptyString | None = None


class RawArtifactProvenance(ContractModel):
    path: NonEmptyString
    role: ArtifactRole
    size_bytes: Annotated[int, Field(ge=0)]
    digest: Sha256Digest


class Source(ContractModel):
    kind: Literal["perf-eval"]
    revision: NonEmptyString | None = None
    artifacts: tuple[RawArtifactProvenance, ...] = ()
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class Vllm(ContractModel):
    commit: NonEmptyString | None = None
    image: NonEmptyString | None = None

    @model_validator(mode="after")
    def require_identity(self) -> Self:
        if self.commit is None and self.image is None:
            raise ValueError("at least one of commit or image is required")
        return self


class Run(ContractModel):
    started_at: datetime
    completed_at: datetime
    status: Literal["completed"]
    runner: Runner
    source: Source
    vllm: Vllm

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        return self


class Workload(ContractModel):
    name: NonEmptyString
    recipe_digest: Sha256Digest
    model: NonEmptyString
    reference: NonEmptyString | None = None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class Environment(ContractModel):
    accelerator: NonEmptyString
    accelerator_count: Annotated[int, Field(gt=0)]
    precision: NonEmptyString | None = None
    topology: NonEmptyString | None = None
    tensor_parallel_size: Annotated[int, Field(gt=0)] | None = None
    data_parallel_size: Annotated[int, Field(gt=0)] | None = None
    extensions: dict[str, JsonValue] = Field(default_factory=dict)


class Metric(ContractModel):
    name: MetricName
    value: float
    unit: NonEmptyString
    aggregation: MetricAggregation


class ObservationSource(ContractModel):
    adapter: Literal["perf-eval"]
    adapter_version: NonEmptyString


class Observation(ContractModel):
    observation_id: NonEmptyString
    kind: ObservationKind
    subject: dict[str, JsonValue]
    configuration: dict[str, JsonValue]
    metrics: Annotated[tuple[Metric, ...], Field(min_length=1)]
    source: ObservationSource

    @model_validator(mode="after")
    def require_unique_metrics(self) -> Self:
        identities = [(metric.name, metric.aggregation) for metric in self.metrics]
        if len(identities) != len(set(identities)):
            raise ValueError("metric name and aggregation pairs must be unique")
        return self


class Bundle(ContractModel):
    schema_version: Literal["v1"]
    bundle_id: UUID
    idempotency_key: Sha256Digest
    run: Run
    workload: Workload
    environment: Environment
    observations: Annotated[tuple[Observation, ...], Field(min_length=1)]
    labels: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_unique_observations(self) -> Self:
        observation_ids = [observation.observation_id for observation in self.observations]
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("observation_id values must be unique")
        return self

    def canonical_json(self, *, include_idempotency_key: bool = True) -> bytes:
        excluded = set() if include_idempotency_key else {"bundle_id", "idempotency_key"}
        data: dict[str, Any] = self.model_dump(mode="json", exclude=excluded)
        return json.dumps(
            data,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()

    def calculated_idempotency_key(self) -> str:
        digest = hashlib.sha256(self.canonical_json(include_idempotency_key=False)).hexdigest()
        return f"sha256:{digest}"

    def has_valid_idempotency_key(self) -> bool:
        return self.idempotency_key == self.calculated_idempotency_key()
