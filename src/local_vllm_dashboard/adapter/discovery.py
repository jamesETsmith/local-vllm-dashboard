from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from local_vllm_dashboard.adapter.perf_eval import find_bench_config, load_mapping


@dataclass(frozen=True)
class ConfigMatch:
    config_name: str
    results: tuple[Path, ...]


@dataclass(frozen=True)
class WorkloadMatch:
    recipe_path: Path
    workload_name: str
    configs: tuple[ConfigMatch, ...]


@dataclass(frozen=True)
class DiscoveryReport:
    workloads: tuple[WorkloadMatch, ...]
    unmatched_results: tuple[Path, ...]
    invalid_files: tuple[tuple[Path, str], ...]

    @property
    def config_count(self) -> int:
        return sum(len(workload.configs) for workload in self.workloads)

    @property
    def result_count(self) -> int:
        configs = (config for workload in self.workloads for config in workload.configs)
        return sum(len(config.results) for config in configs)


def yaml_files(root: Path) -> tuple[Path, ...]:
    return tuple(sorted((*root.rglob("*.yaml"), *root.rglob("*.yml"))))


def json_files(root: Path) -> tuple[Path, ...]:
    return tuple(sorted(root.rglob("*.json")))


def config_identity(config: dict[str, Any]) -> tuple[object, object]:
    return config.get("max_concurrency"), config.get("num_prompts")


def result_scope(
    recipe_path: Path,
    workload_name: str,
    results_dir: Path,
    results: list[tuple[Path, dict[str, Any]]],
    recipe_paths: tuple[Path, ...],
) -> list[tuple[Path, dict[str, Any]]]:
    preferred_root = results_dir / workload_name
    if preferred_root.is_dir():
        return [(path, result) for path, result in results if path.is_relative_to(preferred_root)]
    stem = recipe_path.stem
    for suffix in ("-workload", "_workload"):
        if stem.endswith(suffix):
            prefix = stem.removesuffix(suffix)
            exact = [
                (path, result)
                for path, result in results
                if path.stem in {f"{prefix}-bench", f"{prefix}_bench"}
            ]
            if exact:
                return exact
            has_other_attempt_recipe = any(
                other.stem.startswith(f"{prefix}-attempt-")
                for other in recipe_paths
                if other != recipe_path
            )
            if has_other_attempt_recipe:
                return []
            return [(path, result) for path, result in results if path.stem.startswith(prefix)]
    return results


def discover(workloads_dir: Path, results_dir: Path) -> DiscoveryReport:
    invalid: list[tuple[Path, str]] = []
    recipes: list[tuple[Path, dict[str, Any]]] = []
    for path in yaml_files(workloads_dir):
        try:
            recipe = load_mapping(path)
            if not recipe.get("name") or not recipe.get("vllm_bench", {}).get("configs"):
                continue
            recipes.append((path, recipe))
        except (OSError, ValueError, TypeError) as error:
            invalid.append((path, str(error)))

    parsed_results: list[tuple[Path, dict[str, Any]]] = []
    for path in json_files(results_dir):
        try:
            result = load_mapping(path)
            if "max_concurrency" not in result or "num_prompts" not in result:
                continue
            parsed_results.append((path, result))
        except (OSError, ValueError, TypeError) as error:
            invalid.append((path, str(error)))

    claimed: set[Path] = set()
    workloads: list[WorkloadMatch] = []
    recipe_paths = tuple(path for path, _ in recipes)
    for recipe_path, recipe in recipes:
        configs = recipe["vllm_bench"]["configs"]
        workload_name = str(recipe["name"])
        scoped_results = result_scope(
            recipe_path,
            workload_name,
            results_dir,
            parsed_results,
            recipe_paths,
        )
        config_matches = []
        for config in configs:
            identity = config_identity(config)
            candidates = []
            for result_path, result in scoped_results:
                if config_identity(result) != identity:
                    continue
                try:
                    find_bench_config(recipe, result)
                except ValueError:
                    continue
                candidates.append(result_path)
            config_matches.append(
                ConfigMatch(config_name=str(config["name"]), results=tuple(sorted(candidates)))
            )
            claimed.update(candidates)
        workloads.append(
            WorkloadMatch(
                recipe_path=recipe_path,
                workload_name=workload_name,
                configs=tuple(config_matches),
            )
        )

    return DiscoveryReport(
        workloads=tuple(workloads),
        unmatched_results=tuple(path for path, _ in parsed_results if path not in claimed),
        invalid_files=tuple(sorted(invalid, key=lambda item: item[0])),
    )
