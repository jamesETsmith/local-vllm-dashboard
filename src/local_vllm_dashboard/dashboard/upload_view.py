from dataclasses import dataclass
from pathlib import Path

from local_vllm_dashboard.adapter import DiscoveryReport


@dataclass(frozen=True)
class UploadConfigView:
    name: str
    status: str
    results: tuple[str, ...]


@dataclass(frozen=True)
class UploadWorkloadView:
    recipe: str
    name: str
    configs: tuple[UploadConfigView, ...]


@dataclass(frozen=True)
class UploadReportView:
    workload_count: int
    config_count: int
    result_count: int
    workloads: tuple[UploadWorkloadView, ...]
    unmatched: tuple[str, ...]
    invalid: tuple[tuple[str, str], ...]


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def upload_report_view(report: DiscoveryReport, root: Path) -> UploadReportView:
    workloads = tuple(
        UploadWorkloadView(
            recipe=relative(workload.recipe_path, root),
            name=workload.workload_name,
            configs=tuple(
                UploadConfigView(
                    name=config.config_name,
                    status=(
                        "missing"
                        if not config.results
                        else "repeated"
                        if len(config.results) > 1
                        else "matched"
                    ),
                    results=tuple(relative(result, root) for result in config.results),
                )
                for config in workload.configs
            ),
        )
        for workload in report.workloads
    )
    return UploadReportView(
        workload_count=len(report.workloads),
        config_count=report.config_count,
        result_count=report.result_count,
        workloads=workloads,
        unmatched=tuple(relative(path, root) for path in report.unmatched_results),
        invalid=tuple((relative(path, root), error) for path, error in report.invalid_files),
    )
