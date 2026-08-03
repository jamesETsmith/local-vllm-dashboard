from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any, cast
from uuid import UUID

import yaml
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers.data import JsonLexer, YamlLexer
from pygments.lexers.shell import BashLexer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from local_vllm_dashboard.dashboard.models import (
    AccuracyView,
    DashboardData,
    DashboardFilters,
    FilterOptions,
    MetricView,
    PerformanceView,
    RunDataRow,
    RunDetailView,
    RunView,
    SourceArtifactView,
)
from local_vllm_dashboard.db.models import ArtifactRecord, BundleRecord, ObservationRecord


def optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError("expected an ISO datetime")


def mapping(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def metric_value(observation: ObservationRecord, name: str) -> float | None:
    return next((metric.value for metric in observation.metrics if metric.name == name), None)


def metrics_view(observation: ObservationRecord) -> tuple[MetricView, ...]:
    return tuple(
        MetricView(
            name=metric.name,
            value=metric.value,
            unit=metric.unit,
            aggregation=metric.aggregation,
        )
        for metric in sorted(observation.metrics, key=lambda item: (item.name, item.aggregation))
    )


def unique_sorted(values: Iterable[str | None]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value is not None}))


def unique_sorted_int(values: Iterable[int | None]) -> tuple[int, ...]:
    return tuple(sorted({value for value in values if value is not None}))


class LiteralBlockDumper(yaml.SafeDumper):
    pass


def literal_string_representer(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


LiteralBlockDumper.add_representer(str, literal_string_representer)


def split_cli_flags(value: str) -> str:
    parts = value.split()
    lines = []
    current = []
    for part in parts:
        if part.startswith("--") and current:
            lines.append(" ".join(current))
            current = [part]
        else:
            current.append(part)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def pretty_artifact(code: str, media_type: str) -> str:
    if media_type == "application/yaml":
        value = yaml.safe_load(code)
        if isinstance(value, dict):
            vllm = value.get("vllm")
            if isinstance(vllm, dict) and isinstance(vllm.get("serve_args"), str):
                vllm["serve_args"] = split_cli_flags(vllm["serve_args"])
        formatted = yaml.dump(
            value,
            Dumper=LiteralBlockDumper,
            sort_keys=False,
            default_flow_style=False,
            width=1000,
        )
        return formatted.replace("serve_args: |-", "serve_args: >-")
    return json.dumps(json.loads(code), indent=2, sort_keys=False) + "\n"


def highlighted(code: str, media_type: str) -> str:
    lexer = YamlLexer() if media_type == "application/yaml" else JsonLexer()
    return highlight(code, lexer, HtmlFormatter(nowrap=True))


def artifact_title(role: str) -> tuple[str, str]:
    if role == "workload_recipe":
        return (
            "perf-eval workload YAML",
            "Original perf-eval recipe used to configure and launch this benchmark.",
        )
    return (
        "Transformed / extracted source data",
        "Original benchmark result JSON used by the client to produce canonical metrics.",
    )


def reproduction_command(artifacts: list[ArtifactRecord]) -> str | None:
    recipe = next(
        (artifact.path for artifact in artifacts if artifact.role == "workload_recipe"),
        None,
    )
    if recipe is None:
        return None
    return f"./lib/run.sh {recipe}"


class DashboardRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def load(self, filters: DashboardFilters | None = None) -> DashboardData:
        selected_filters = filters or DashboardFilters()
        bundles = self.session.scalars(
            select(BundleRecord)
            .options(
                selectinload(BundleRecord.artifacts),
                selectinload(BundleRecord.dependency_revisions),
                selectinload(BundleRecord.observations).selectinload(ObservationRecord.metrics),
            )
            .order_by(BundleRecord.accepted_at.desc())
        ).all()
        all_performance = tuple(
            view
            for bundle in bundles
            for observation in bundle.observations
            if observation.kind == "performance"
            for view in (self.performance_view(bundle, observation),)
        )
        all_accuracy = tuple(
            view
            for bundle in bundles
            for observation in bundle.observations
            if observation.kind == "accuracy"
            for view in (self.accuracy_view(bundle, observation),)
        )
        performance = tuple(
            view for view in all_performance if self.matches_performance(view, selected_filters)
        )
        accuracy = tuple(
            view for view in all_accuracy if self.matches_accuracy(view, selected_filters)
        )
        runs = tuple(
            self.run_view(bundle)
            for bundle in bundles
            if self.matches_run(self.run_view(bundle), selected_filters)
        )
        run_data = tuple(
            self.run_data_view(bundle, observation)
            for bundle in bundles
            for observation in bundle.observations
            if observation.kind == "performance"
            and self.matches_performance(
                self.performance_view(bundle, observation),
                selected_filters,
            )
        )
        return DashboardData(
            performance=performance,
            accuracy=accuracy,
            runs=runs,
            run_data=run_data,
            options=self.filter_options(all_performance, all_accuracy),
        )

    def detail(self, bundle_id: UUID) -> RunDetailView | None:
        bundle = self.session.scalar(
            select(BundleRecord)
            .where(BundleRecord.bundle_id == bundle_id)
            .options(
                selectinload(BundleRecord.artifacts),
                selectinload(BundleRecord.dependency_revisions),
                selectinload(BundleRecord.observations).selectinload(ObservationRecord.metrics),
            )
        )
        if bundle is None:
            return None
        observations = sorted(
            bundle.observations,
            key=lambda observation: observation.observation_id,
        )
        artifact_records = sorted(bundle.artifacts, key=lambda artifact: artifact.path)
        command = reproduction_command(artifact_records)
        payload_json = json.dumps(bundle.payload, indent=2, sort_keys=True)
        return RunDetailView(
            run=self.run_view(bundle),
            reproduction_command=command,
            reproduction_command_html=(
                highlight(command, BashLexer(), HtmlFormatter(nowrap=True)) if command else None
            ),
            payload_json=payload_json,
            payload_json_html=highlight(payload_json, JsonLexer(), HtmlFormatter(nowrap=True)),
            configuration_json=tuple(
                json.dumps(observation.configuration, indent=2, sort_keys=True)
                for observation in observations
            ),
            subject_json=tuple(
                json.dumps(observation.subject, indent=2, sort_keys=True)
                for observation in observations
            ),
            source_json=tuple(
                json.dumps(observation.source, indent=2, sort_keys=True)
                for observation in observations
            ),
            metrics=tuple(metrics_view(observation) for observation in observations),
            artifacts=tuple(
                SourceArtifactView(
                    path=artifact.path,
                    role=artifact.role,
                    title=artifact_title(artifact.role)[0],
                    description=artifact_title(artifact.role)[1],
                    media_type=artifact.media_type,
                    size_bytes=artifact.size_bytes,
                    digest=artifact.digest,
                    text=pretty_artifact(
                        artifact.content.decode("utf-8"),
                        artifact.media_type,
                    ),
                    highlighted_html=highlighted(
                        pretty_artifact(
                            artifact.content.decode("utf-8"),
                            artifact.media_type,
                        ),
                        artifact.media_type,
                    ),
                )
                for artifact in artifact_records
            ),
        )

    def performance_view(
        self,
        bundle: BundleRecord,
        observation: ObservationRecord,
    ) -> PerformanceView:
        payload = bundle.payload
        environment = mapping(payload.get("environment"))
        environment_extensions = mapping(environment.get("extensions"))
        workload = mapping(payload.get("workload"))
        run = mapping(payload.get("run"))
        configuration = observation.configuration
        return PerformanceView(
            bundle_id=bundle.bundle_id,
            completed_at=parse_datetime(run.get("completed_at")),
            hardware=str(environment.get("accelerator", "unknown")),
            accelerator_count=int(environment.get("accelerator_count", 0)),
            model=str(workload.get("model", "unknown")),
            workload=str(workload.get("name", "unknown")),
            precision=optional_string(environment.get("precision")),
            tensor_parallel_size=optional_int(environment.get("tensor_parallel_size")),
            data_parallel_size=optional_int(environment.get("data_parallel_size")),
            expert_parallel=environment_extensions.get("expert_parallel") is True,
            input_tokens=optional_int(configuration.get("input_tokens")),
            output_tokens=optional_int(configuration.get("output_tokens")),
            prefix_cache_tokens=optional_int(configuration.get("prefix_cache_tokens")),
            concurrency=optional_int(configuration.get("max_concurrency")),
            completed_requests=optional_int(configuration.get("completed")),
            failed_requests=optional_int(configuration.get("failed")),
            metrics=metrics_view(observation),
        )

    def run_data_view(
        self,
        bundle: BundleRecord,
        observation: ObservationRecord,
    ) -> RunDataRow:
        payload = bundle.payload
        environment = mapping(payload.get("environment"))
        environment_extensions = mapping(environment.get("extensions"))
        workload = mapping(payload.get("workload"))
        run = mapping(payload.get("run"))
        vllm = mapping(run.get("vllm"))
        configuration = observation.configuration
        return RunDataRow(
            bundle_id=bundle.bundle_id,
            completed_at=parse_datetime(run.get("completed_at")),
            hardware=str(environment.get("accelerator", "unknown")),
            accelerator_count=int(environment.get("accelerator_count", 0)),
            model=str(workload.get("model", "unknown")),
            precision=optional_string(environment.get("precision")),
            tensor_parallel_size=optional_int(environment.get("tensor_parallel_size")),
            data_parallel_size=optional_int(environment.get("data_parallel_size")),
            expert_parallel=environment_extensions.get("expert_parallel") is True,
            input_tokens=optional_int(configuration.get("input_tokens")),
            output_tokens=optional_int(configuration.get("output_tokens")),
            prefix_cache_tokens=optional_int(configuration.get("prefix_cache_tokens")),
            concurrency=optional_int(configuration.get("max_concurrency")),
            completed_requests=optional_int(configuration.get("completed")),
            failed_requests=optional_int(configuration.get("failed")),
            total_token_throughput_per_gpu=metric_value(
                observation, "total_token_throughput_per_gpu"
            ),
            output_token_throughput_per_gpu=metric_value(
                observation, "output_token_throughput_per_gpu"
            ),
            request_throughput_per_gpu=metric_value(observation, "request_throughput_per_gpu"),
            mean_ttft=metric_value(observation, "mean_ttft"),
            p99_ttft=metric_value(observation, "p99_ttft"),
            mean_tpot=metric_value(observation, "mean_tpot"),
            p99_tpot=metric_value(observation, "p99_tpot"),
            mean_itl=metric_value(observation, "mean_itl"),
            p99_itl=metric_value(observation, "p99_itl"),
            mean_e2el=metric_value(observation, "mean_e2el"),
            p99_e2el=metric_value(observation, "p99_e2el"),
            vllm_image=optional_string(vllm.get("image")),
            vllm_commit=optional_string(vllm.get("commit")),
            dependency_revisions=tuple(
                (revision.name.removesuffix("_commit"), revision.revision)
                for revision in sorted(bundle.dependency_revisions, key=lambda item: item.name)
            ),
        )

    def accuracy_view(
        self,
        bundle: BundleRecord,
        observation: ObservationRecord,
    ) -> AccuracyView:
        payload = bundle.payload
        environment = mapping(payload.get("environment"))
        workload = mapping(payload.get("workload"))
        run = mapping(payload.get("run"))
        configuration = observation.configuration
        return AccuracyView(
            bundle_id=bundle.bundle_id,
            completed_at=parse_datetime(run.get("completed_at")),
            hardware=str(environment.get("accelerator", "unknown")),
            model=str(workload.get("model", "unknown")),
            workload=str(workload.get("name", "unknown")),
            task=optional_string(observation.subject.get("task")) or "unknown",
            fewshot=optional_int(configuration.get("num_fewshot")) or 0,
            partial=configuration.get("partial") is True,
            metrics=metrics_view(observation),
        )

    def run_view(self, bundle: BundleRecord) -> RunView:
        payload = bundle.payload
        environment = mapping(payload.get("environment"))
        workload = mapping(payload.get("workload"))
        run = mapping(payload.get("run"))
        vllm = mapping(run.get("vllm"))
        source = mapping(run.get("source"))
        source_extensions = mapping(source.get("extensions"))
        runner = mapping(run.get("runner"))
        return RunView(
            bundle_id=bundle.bundle_id,
            accepted_at=bundle.accepted_at,
            completed_at=parse_datetime(run.get("completed_at")),
            workload=str(workload.get("name", "unknown")),
            model=str(workload.get("model", "unknown")),
            hardware=str(environment.get("accelerator", "unknown")),
            accelerator_count=int(environment.get("accelerator_count", 0)),
            vllm_image=optional_string(vllm.get("image")),
            vllm_commit=optional_string(vllm.get("commit")),
            dependency_revisions=tuple(
                (revision.name.removesuffix("_commit"), revision.revision)
                for revision in sorted(bundle.dependency_revisions, key=lambda item: item.name)
            ),
            container=optional_string(source_extensions.get("container")),
            runner_kind=str(runner.get("kind", "unknown")),
            observation_count=len(bundle.observations),
            artifact_count=len(bundle.artifacts),
        )

    @staticmethod
    def matches_performance(view: PerformanceView, filters: DashboardFilters) -> bool:
        return (
            (filters.hardware is None or view.hardware == filters.hardware)
            and (filters.model is None or view.model == filters.model)
            and (filters.input_tokens is None or view.input_tokens == filters.input_tokens)
            and (filters.output_tokens is None or view.output_tokens == filters.output_tokens)
            and (
                filters.prefix_cache_tokens is None
                or view.prefix_cache_tokens == filters.prefix_cache_tokens
            )
            and (filters.concurrency is None or view.concurrency == filters.concurrency)
            and (filters.precision is None or view.precision == filters.precision)
        )

    @staticmethod
    def matches_accuracy(view: AccuracyView, filters: DashboardFilters) -> bool:
        return (
            (filters.hardware is None or view.hardware == filters.hardware)
            and (filters.model is None or view.model == filters.model)
            and (filters.task is None or view.task == filters.task)
        )

    @staticmethod
    def matches_run(view: RunView, filters: DashboardFilters) -> bool:
        return (filters.hardware is None or view.hardware == filters.hardware) and (
            filters.model is None or view.model == filters.model
        )

    @staticmethod
    def filter_options(
        performance: tuple[PerformanceView, ...],
        accuracy: tuple[AccuracyView, ...],
    ) -> FilterOptions:
        return FilterOptions(
            hardware=unique_sorted(
                [view.hardware for view in performance] + [view.hardware for view in accuracy]
            ),
            models=unique_sorted(
                [view.model for view in performance] + [view.model for view in accuracy]
            ),
            input_tokens=unique_sorted_int(view.input_tokens for view in performance),
            output_tokens=unique_sorted_int(view.output_tokens for view in performance),
            prefix_cache_tokens=unique_sorted_int(view.prefix_cache_tokens for view in performance),
            concurrencies=unique_sorted_int(view.concurrency for view in performance),
            precisions=unique_sorted(view.precision for view in performance),
            tasks=unique_sorted(view.task for view in accuracy),
        )
