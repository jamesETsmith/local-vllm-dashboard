from __future__ import annotations

import io
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from local_vllm_dashboard.adapter import DiscoveryReport, build_performance_bundle, discover
from local_vllm_dashboard.artifacts import artifact_contents
from local_vllm_dashboard.db import BundleRepository, SaveStatus

ALLOWED_SUFFIXES = {".yaml", ".yml", ".json"}
REVISION_SUFFIX = ".revisions.json"
MAX_FILES = 500
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class UploadedFile:
    path: str
    content: bytes


@dataclass(frozen=True)
class UploadPreview:
    upload_id: str
    report: DiscoveryReport
    root: Path


@dataclass(frozen=True)
class UploadResult:
    accepted: int
    duplicate: int
    failed: tuple[tuple[Path, str], ...]


def safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe path: {value}")
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ValueError(f"unsupported file type: {value}")
    if path.name.endswith(REVISION_SUFFIX) and len(path.parts) < 2:
        raise ValueError(f"revision metadata must be stored beside a workload: {value}")
    return path


def archive_files(content: bytes) -> tuple[UploadedFile, ...]:
    files = []
    total = 0
    try:
        archive = tarfile.open(fileobj=io.BytesIO(content), mode="r:*")
    except tarfile.TarError as error:
        raise ValueError("invalid tar archive") from error
    with archive:
        unsupported = []
        for member in archive.getmembers():
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"unsupported archive member: {member.name}")
            if PurePosixPath(member.name).suffix.lower() not in ALLOWED_SUFFIXES:
                unsupported.append(member.name)
                continue
            path = safe_relative_path(member.name)
            if member.size > MAX_FILE_BYTES:
                raise ValueError(f"file is too large: {member.name}")
            total += member.size
            if total > MAX_TOTAL_BYTES or len(files) >= MAX_FILES:
                raise ValueError("upload exceeds file count or total size limit")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError(f"could not read archive member: {member.name}")
            files.append(UploadedFile(str(path), extracted.read()))
    if not files and unsupported:
        preview = ", ".join(unsupported[:5])
        raise ValueError(f"archive contains no YAML or JSON files; unsupported: {preview}")
    return tuple(files)


def validate_files(files: tuple[UploadedFile, ...]) -> tuple[UploadedFile, ...]:
    if not files:
        raise ValueError("no supported files were uploaded")
    if len(files) > MAX_FILES:
        raise ValueError("too many uploaded files")
    total = 0
    checked = []
    seen = set()
    for item in files:
        path = safe_relative_path(item.path)
        if len(item.content) > MAX_FILE_BYTES:
            raise ValueError(f"file is too large: {item.path}")
        total += len(item.content)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("upload exceeds total size limit")
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        if str(path) in seen:
            raise ValueError(f"duplicate uploaded path: {item.path}")
        seen.add(str(path))
        checked.append(UploadedFile(str(path), item.content))
    if not checked:
        raise ValueError("no supported YAML or JSON files were uploaded")
    return tuple(checked)


def stage_upload(files: tuple[UploadedFile, ...], staging_root: Path) -> UploadPreview:
    checked = validate_files(files)
    staging_root.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="upload-", dir=staging_root))
    for item in checked:
        target = root.joinpath(*PurePosixPath(item.path).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.content)
    report = discover(root, root)
    return UploadPreview(upload_id=root.name, report=report, root=root)


def load_preview(upload_id: str, staging_root: Path) -> UploadPreview:
    if not upload_id.startswith("upload-") or "/" in upload_id or ".." in upload_id:
        raise ValueError("invalid upload identifier")
    root = staging_root / upload_id
    if not root.is_dir():
        raise ValueError("upload preview has expired")
    return UploadPreview(upload_id=upload_id, report=discover(root, root), root=root)


def ingest_preview(preview: UploadPreview, repository: BundleRepository) -> UploadResult:
    accepted = 0
    duplicate = 0
    failed = []
    for workload in preview.report.workloads:
        for config in workload.configs:
            for result_path in config.results:
                try:
                    bundle = build_performance_bundle(workload.recipe_path, result_path)
                    artifacts = artifact_contents(bundle, (workload.recipe_path, result_path))
                    outcome = repository.save(bundle, artifacts)
                    if outcome.status == SaveStatus.ACCEPTED:
                        accepted += 1
                    else:
                        duplicate += 1
                except Exception as error:
                    repository.session.rollback()
                    failed.append((result_path, str(error)))
    return UploadResult(accepted=accepted, duplicate=duplicate, failed=tuple(failed))
