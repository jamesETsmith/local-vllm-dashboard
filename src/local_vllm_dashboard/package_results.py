from __future__ import annotations

import io
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from local_vllm_dashboard.adapter import DiscoveryReport, discover
from local_vllm_dashboard.adapter.perf_eval import load_mapping
from local_vllm_dashboard.container_revisions import (
    ContainerRevisions,
    discover_revisions,
    revisions_json,
)


@dataclass(frozen=True)
class PackageSummary:
    archive: Path
    workloads: int
    results: int
    revisions: int


def archive_path(path: Path, root: Path, prefix: str) -> PurePosixPath:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{path} is outside {root}") from error
    return PurePosixPath(prefix, *relative.parts)


def revision_path(recipe_path: Path, workloads_dir: Path) -> PurePosixPath:
    recipe = archive_path(recipe_path, workloads_dir, "workloads")
    return recipe.with_name(f"{recipe.stem}.revisions.json")


def create_results_archive(
    workloads_dir: Path,
    results_dir: Path,
    output: Path,
    *,
    container: str | None = None,
    revision_overrides: dict[Path, ContainerRevisions] | None = None,
) -> tuple[DiscoveryReport, PackageSummary]:
    report = discover(workloads_dir, results_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    revision_count = 0
    with tarfile.open(output, mode="w:gz") as archive:
        added: set[Path] = set()
        for workload in report.workloads:
            recipe_path = workload.recipe_path
            archive.add(
                recipe_path, arcname=str(archive_path(recipe_path, workloads_dir, "workloads"))
            )
            recipe = load_mapping(recipe_path)
            vllm = recipe["vllm"]
            gpu = str(recipe["gpu"])
            revisions = (revision_overrides or {}).get(recipe_path) or discover_revisions(
                workload.workload_name,
                str(vllm["image"]),
                is_rocm=gpu.upper().startswith("MI"),
                container=container,
            )
            if revisions.vllm_commit or revisions.aiter_commit:
                metadata = revisions_json(revisions)
                info = tarfile.TarInfo(str(revision_path(recipe_path, workloads_dir)))
                info.size = len(metadata)
                info.mode = 0o644
                archive.addfile(info, fileobj=io.BytesIO(metadata))
                revision_count += 1
            for config in workload.configs:
                for result_path in config.results:
                    if result_path in added:
                        continue
                    archive.add(
                        result_path,
                        arcname=str(archive_path(result_path, results_dir, "results")),
                    )
                    added.add(result_path)
    summary = PackageSummary(
        archive=output,
        workloads=len(report.workloads),
        results=report.result_count,
        revisions=revision_count,
    )
    return report, summary
