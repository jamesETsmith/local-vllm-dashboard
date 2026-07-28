from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from local_vllm_dashboard.adapter import DiscoveryReport, build_performance_bundle, discover
from local_vllm_dashboard.artifacts import artifact_contents
from local_vllm_dashboard.publisher import Publisher


@dataclass(frozen=True)
class PublishSummary:
    accepted: int
    duplicate: int
    failed: tuple[tuple[Path, str], ...]


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def render_report(report: DiscoveryReport, workloads_dir: Path, results_dir: Path) -> str:
    lines = [
        "Discovery report",
        f"  Workload files: {len(report.workloads)}",
        f"  Benchmark configs: {report.config_count}",
        f"  Matched results: {report.result_count}",
    ]
    for workload in report.workloads:
        recipe_name = relative(workload.recipe_path, workloads_dir)
        lines.append(f"\n{recipe_name} ({workload.workload_name})")
        for config in workload.configs:
            if not config.results:
                lines.append(f"  MISSING  {config.config_name}")
            elif len(config.results) == 1:
                lines.append(
                    f"  MATCHED  {config.config_name} -> {relative(config.results[0], results_dir)}"
                )
            else:
                lines.append(f"  REPEATED {config.config_name} ({len(config.results)} results)")
                lines.extend(
                    f"           - {relative(result, results_dir)}" for result in config.results
                )
    if report.unmatched_results:
        lines.append(f"\nUnmatched results ({len(report.unmatched_results)}):")
        lines.extend(f"  - {relative(path, results_dir)}" for path in report.unmatched_results)
    if report.invalid_files:
        lines.append(f"\nInvalid files ({len(report.invalid_files)}):")
        lines.extend(f"  - {path}: {error}" for path, error in report.invalid_files)
    return "\n".join(lines)


def publish_report(
    report: DiscoveryReport,
    endpoint: str,
    token: str,
    container: str | None = None,
) -> PublishSummary:
    accepted = 0
    duplicate = 0
    failed = []
    with Publisher(endpoint, token=token) as publisher:
        for workload in report.workloads:
            for config in workload.configs:
                for result_path in config.results:
                    try:
                        bundle = build_performance_bundle(
                            workload.recipe_path,
                            result_path,
                            container=container,
                        )
                        artifacts = artifact_contents(
                            bundle,
                            (workload.recipe_path, result_path),
                        )
                        outcome = publisher.publish(bundle, artifacts)
                        if outcome.status == "accepted":
                            accepted += 1
                        else:
                            duplicate += 1
                    except Exception as error:
                        failed.append((result_path, str(error)))
    return PublishSummary(accepted=accepted, duplicate=duplicate, failed=tuple(failed))


def ingest_directories(
    workloads_dir: Path,
    results_dir: Path,
    endpoint: str | None,
    token: str | None = None,
    container: str | None = None,
) -> tuple[DiscoveryReport, PublishSummary | None]:
    report = discover(workloads_dir, results_dir)
    if endpoint and not token:
        raise ValueError("ingestion token is required when publishing")
    can_publish = endpoint is not None and token is not None
    summary = publish_report(report, endpoint, token, container=container) if can_publish else None
    return report, summary
