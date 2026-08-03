import json
from pathlib import Path

import pytest

from local_vllm_dashboard.container_revisions import (
    ContainerRevisions,
    discover_container,
    discover_revisions,
    extract_image_revisions,
    extract_revisions,
    load_revisions,
    write_revisions,
)


def test_extract_returns_empty_when_container_is_missing() -> None:
    result = extract_revisions("nonexistent-container-xyz")

    assert result == ContainerRevisions()


def test_extract_returns_empty_for_blank_container() -> None:
    assert extract_revisions("") == ContainerRevisions()


def test_discover_container_requires_unique_name_and_image(monkeypatch) -> None:
    output = "\n".join(
        (
            '{"Names":"perf-eval-demo-123","Image":"example/image"}',
            '{"Names":"other","Image":"example/image"}',
        )
    )
    monkeypatch.setattr(
        "local_vllm_dashboard.container_revisions._output",
        lambda *_args, **_kwargs: output,
    )

    assert discover_container("demo", "example/image") == "perf-eval-demo-123"


def test_extract_image_uses_local_image_label(monkeypatch) -> None:
    responses = iter(("sha256:image", "abcdef0"))
    monkeypatch.setattr(
        "local_vllm_dashboard.container_revisions._output",
        lambda *_args, **_kwargs: next(responses),
    )

    revisions = extract_image_revisions("example/image", is_rocm=False)

    assert revisions.vllm_commit == "abcdef0"
    assert revisions.aiter_commit is None


def test_discovery_falls_back_to_local_image(monkeypatch) -> None:
    monkeypatch.setattr(
        "local_vllm_dashboard.container_revisions.discover_container",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "local_vllm_dashboard.container_revisions.extract_image_revisions",
        lambda *_args, **_kwargs: ContainerRevisions(vllm_commit="abcdef0"),
    )

    revisions = discover_revisions("demo", "example/image", is_rocm=False)

    assert revisions.vllm_commit == "abcdef0"


def test_extract_reads_vllm_and_aiter_commits(monkeypatch) -> None:
    responses = iter(
        (
            "true",
            "abcdef0",
            "fedcba0",
        )
    )
    monkeypatch.setattr(
        "local_vllm_dashboard.container_revisions._output",
        lambda *_args, **_kwargs: next(responses),
    )

    revisions = extract_revisions("perf-eval-demo-123", is_rocm=True)

    assert revisions == ContainerRevisions(
        container="perf-eval-demo-123",
        vllm_commit="abcdef0",
        aiter_commit="fedcba0",
    )


def test_revision_metadata_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "demo.revisions.json"
    revisions = ContainerRevisions(
        container="perf-eval-demo-123",
        vllm_commit="abcdef0",
        aiter_commit="fedcba0",
    )

    write_revisions(path, revisions)

    assert load_revisions(path) == revisions


def test_revision_metadata_rejects_invalid_commits(tmp_path: Path) -> None:
    path = tmp_path / "demo.revisions.json"
    path.write_text(json.dumps({"vllm_commit": "not-a-commit"}))

    with pytest.raises(ValueError, match="invalid vllm_commit"):
        load_revisions(path)
