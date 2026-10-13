from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.parse import quote

import httpx

PERF_EVAL_REPOSITORY = "https://github.com/vllm-project/perf-eval"


@dataclass(frozen=True)
class ReproductionArtifact:
    path: str
    role: str
    media_type: str
    size_bytes: int
    digest: str
    content: str


@dataclass(frozen=True)
class ReproductionRecipe:
    observation_id: str
    server_command: str
    benchmark_command: str


@dataclass(frozen=True)
class Reproduction:
    bundle_id: str
    workload: str
    model: str
    hardware: str
    vllm_image: str
    vllm_commit: str | None
    dependency_revisions: tuple[tuple[str, str], ...]
    perf_eval_command: str | None
    recipes: tuple[ReproductionRecipe, ...]
    artifacts: tuple[ReproductionArtifact, ...]

    @property
    def workload_recipe(self) -> ReproductionArtifact | None:
        return next(
            (artifact for artifact in self.artifacts if artifact.role == "workload_recipe"),
            None,
        )

    @property
    def result_artifacts(self) -> tuple[ReproductionArtifact, ...]:
        return tuple(artifact for artifact in self.artifacts if artifact.role != "workload_recipe")


def _mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _sequence(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _integer(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _revision_map(value: object) -> tuple[tuple[str, str], ...]:
    revisions = []
    for item in _sequence(value):
        if isinstance(item, (list, tuple)) and len(item) == 2:
            revisions.append((str(item[0]), str(item[1])))
    return tuple(revisions)


def _parse_result(payload: dict[str, object]) -> Reproduction:
    run = _mapping(payload.get("run"))
    recipes = _sequence(payload.get("recipes"))
    artifacts = _sequence(payload.get("artifacts"))
    return Reproduction(
        bundle_id=_text(run.get("bundle_id")),
        workload=_text(run.get("workload")),
        model=_text(run.get("model")),
        hardware=_text(run.get("hardware")),
        vllm_image=_text(run.get("vllm_image")),
        vllm_commit=_text(run.get("vllm_commit")) or None,
        dependency_revisions=_revision_map(run.get("dependency_revisions")),
        perf_eval_command=_text(payload.get("perf_eval_command")) or None,
        recipes=tuple(
            ReproductionRecipe(
                observation_id=_text(_mapping(recipe).get("observation_id")),
                server_command=_text(_mapping(recipe).get("server_command")),
                benchmark_command=_text(_mapping(recipe).get("benchmark_command")),
            )
            for recipe in recipes
            if isinstance(recipe, dict)
        ),
        artifacts=tuple(
            ReproductionArtifact(
                path=_text(_mapping(artifact).get("path")),
                role=_text(_mapping(artifact).get("role")),
                media_type=_text(_mapping(artifact).get("media_type")),
                size_bytes=_integer(_mapping(artifact).get("size_bytes")),
                digest=_text(_mapping(artifact).get("digest")),
                content=_text(_mapping(artifact).get("content")),
            )
            for artifact in artifacts
            if isinstance(artifact, dict)
        ),
    )


def fetch_reproduction(
    endpoint: str,
    bundle_id: str,
    *,
    client: httpx.Client | None = None,
) -> Reproduction:
    url = f"{endpoint.rstrip('/')}/api/v1/configurations/{quote(bundle_id, safe='')}/reproduction"
    owned = client is None
    selected = client or httpx.Client(timeout=30)
    try:
        response = selected.get(url)
        if response.status_code == httpx.codes.NOT_FOUND:
            raise SystemExit(f"bundle not found: {bundle_id}")
        response.raise_for_status()
        return _parse_result(response.json())
    finally:
        if owned:
            selected.close()


def reproduction_files(reproduction: Reproduction) -> dict[str, str]:
    files: dict[str, str] = {}
    for artifact in reproduction.artifacts:
        files[artifact.path] = artifact.content
    files["reproduction.json"] = json.dumps(
        {
            "bundle_id": reproduction.bundle_id,
            "workload": reproduction.workload,
            "model": reproduction.model,
            "hardware": reproduction.hardware,
            "vllm_image": reproduction.vllm_image,
            "vllm_commit": reproduction.vllm_commit,
            "dependency_revisions": list(reproduction.dependency_revisions),
            "perf_eval_command": reproduction.perf_eval_command,
            "recipes": [
                {
                    "observation_id": recipe.observation_id,
                    "server_command": recipe.server_command,
                    "benchmark_command": recipe.benchmark_command,
                }
                for recipe in reproduction.recipes
            ],
        },
        indent=2,
    )
    return files


def write_reproduction(reproduction: Reproduction, output: Path) -> tuple[Path, ...]:
    output.mkdir(parents=True, exist_ok=True)
    written = []
    for name, content in reproduction_files(reproduction).items():
        destination = output / Path(name).name
        destination.write_text(content)
        written.append(destination)
    return tuple(written)


def render_reproduction(reproduction: Reproduction, output: Path) -> str:
    recipe = reproduction.workload_recipe
    lines = [
        f"Reproduce {reproduction.workload} ({reproduction.model} on {reproduction.hardware})",
        f"  Bundle: {reproduction.bundle_id}",
        f"  vLLM image: {reproduction.vllm_image or 'unknown'}",
        f"  vLLM commit: {reproduction.vllm_commit or 'not detected'}",
    ]
    for name, revision in reproduction.dependency_revisions:
        lines.append(f"  {name.upper()} commit: {revision}")
    lines.append("")
    lines.append("Steps")
    lines.append(f"  1. Install perf-eval: git clone {PERF_EVAL_REPOSITORY} && cd perf-eval")
    if recipe is not None:
        lines.append(f"  2. Copy {output / Path(recipe.path).name} into perf-eval/workloads/")
    else:
        lines.append("  2. Copy the saved workload YAML into perf-eval/workloads/")
    lines.append("  3. Run: " + (reproduction.perf_eval_command or "./lib/run.sh <workload.yaml>"))
    if reproduction.result_artifacts:
        saved = ", ".join(
            str(output / Path(artifact.path).name) for artifact in reproduction.result_artifacts
        )
        lines.append(f"  Saved original result files for comparison: {saved}")
    if reproduction.recipes:
        lines.append("")
        lines.append("Run without perf-eval")
        lines.append("  Start the server:")
        for item in reproduction.recipes:
            lines.append(f"    # {item.observation_id}")
            lines.extend(f"    {line}" for line in item.server_command.splitlines())
        lines.append("  Then run the benchmark:")
        for item in reproduction.recipes:
            lines.append(f"    # {item.observation_id}")
            lines.extend(f"    {line}" for line in item.benchmark_command.splitlines())
    return "\n".join(lines)
