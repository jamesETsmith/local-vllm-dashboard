from __future__ import annotations

import json
import re
import subprocess  # nosec B404
from dataclasses import dataclass

COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


@dataclass(frozen=True)
class ContainerRevisions:
    container: str | None = None
    vllm_commit: str | None = None
    aiter_commit: str | None = None


def _run(arguments: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(  # noqa: S603  # nosec B603
            ["/usr/bin/docker", *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _output(arguments: list[str], timeout: int = 10) -> str | None:
    result = _run(arguments, timeout)
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _commit(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    return candidate if COMMIT_PATTERN.fullmatch(candidate) else None


def discover_container(workload_name: str, image: str) -> str | None:
    output = _output(["ps", "--all", "--format", "{{json .}}"], timeout=5)
    if output is None:
        return None
    prefix = f"perf-eval-{workload_name}-"
    candidates = []
    for line in output.splitlines():
        try:
            container = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = str(container.get("Names", ""))
        container_image = str(container.get("Image", ""))
        if name.startswith(prefix) and container_image == image:
            candidates.append(name)
    return candidates[0] if len(candidates) == 1 else None


def _package_script(package: str) -> str:
    return (
        "import importlib.metadata as m,json,pathlib;"
        f"d=m.distribution('{package}');"
        "p=pathlib.Path(d._path)/'direct_url.json';"
        "x=json.loads(p.read_text()) if p.exists() else {};"
        "print(x.get('vcs_info',{}).get('commit_id',''))"
    )


def _package_commit(container: str, package: str) -> str | None:
    return _commit(_output(["exec", container, "python3", "-c", _package_script(package)]))


def _module_commit(container: str, module: str) -> str | None:
    script = f"import {module};print(getattr({module},'__commit__',''))"
    return _commit(_output(["exec", container, "python3", "-c", script]))


def _git_commit(container: str, directories: tuple[str, ...]) -> str | None:
    for directory in directories:
        value = _output(["exec", container, "git", "-C", directory, "rev-parse", "HEAD"])
        commit = _commit(value)
        if commit:
            return commit
    return None


def _revision_label(target: str, *, image: bool = False) -> str | None:
    value = _output(
        [
            "image" if image else "container",
            "inspect",
            "--format",
            '{{index .Config.Labels "org.opencontainers.image.revision"}}',
            target,
        ],
        timeout=5,
    )
    return _commit(value)


def _image_package_commit(image: str, package: str) -> str | None:
    return _commit(
        _output(
            [
                "run",
                "--rm",
                "--entrypoint",
                "python3",
                image,
                "-c",
                _package_script(package),
            ],
            timeout=30,
        )
    )


def _image_module_commit(image: str, module: str) -> str | None:
    script = f"import {module};print(getattr({module},'__commit__',''))"
    return _commit(
        _output(
            ["run", "--rm", "--entrypoint", "python3", image, "-c", script],
            timeout=30,
        )
    )


def _image_git_commit(image: str, directories: tuple[str, ...]) -> str | None:
    for directory in directories:
        value = _output(
            [
                "run",
                "--rm",
                "--entrypoint",
                "git",
                image,
                "-C",
                directory,
                "rev-parse",
                "HEAD",
            ],
            timeout=30,
        )
        commit = _commit(value)
        if commit:
            return commit
    return None


def extract_image_revisions(image: str, *, is_rocm: bool) -> ContainerRevisions:
    if _output(["image", "inspect", "--format", "{{.Id}}", image], 5) is None:
        return ContainerRevisions()
    vllm_commit = (
        _revision_label(image, image=True)
        or _image_package_commit(image, "vllm")
        or _image_module_commit(image, "vllm")
        or _image_git_commit(image, ("/vllm-workspace", "/workspace/vllm"))
    )
    aiter_commit = None
    if is_rocm:
        aiter_commit = (
            _image_package_commit(image, "aiter")
            or _image_module_commit(image, "aiter")
            or _image_git_commit(image, ("/aiter", "/workspace/aiter"))
        )
    return ContainerRevisions(vllm_commit=vllm_commit, aiter_commit=aiter_commit)


def extract_revisions(
    container: str,
    *,
    is_rocm: bool = False,
) -> ContainerRevisions:
    if not container:
        return ContainerRevisions()
    running = _output(["inspect", "--format", "{{.State.Running}}", container], 5)
    if running != "true":
        image = _output(["inspect", "--format", "{{.Config.Image}}", container], 5)
        if image is None:
            return ContainerRevisions()
        revisions = extract_image_revisions(image, is_rocm=is_rocm)
        return ContainerRevisions(
            container=container,
            vllm_commit=revisions.vllm_commit,
            aiter_commit=revisions.aiter_commit,
        )

    vllm_commit = (
        _module_commit(container, "vllm")
        or _package_commit(container, "vllm")
        or _git_commit(container, ("/vllm-workspace", "/workspace/vllm"))
        or _revision_label(container)
    )
    aiter_commit = None
    if is_rocm:
        aiter_commit = (
            _module_commit(container, "aiter")
            or _package_commit(container, "aiter")
            or _git_commit(container, ("/aiter", "/workspace/aiter"))
        )

    return ContainerRevisions(
        container=container,
        vllm_commit=vllm_commit,
        aiter_commit=aiter_commit,
    )


def discover_revisions(
    workload_name: str,
    image: str,
    *,
    is_rocm: bool,
    container: str | None = None,
) -> ContainerRevisions:
    selected = container or discover_container(workload_name, image)
    if selected is not None:
        revisions = extract_revisions(selected, is_rocm=is_rocm)
        if revisions.vllm_commit or revisions.aiter_commit:
            return revisions
    return extract_image_revisions(image, is_rocm=is_rocm)
