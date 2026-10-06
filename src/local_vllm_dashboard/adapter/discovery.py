from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from local_vllm_dashboard.adapter.perf_eval import (
    expand_bench_configs,
    find_bench_config,
    load_mapping,
)


@dataclass(frozen=True)
class ConfigMatch:
    config_name: str
    results: tuple[Path, ...]


@dataclass(frozen=True)
class AccuracyMatch:
    task_name: str
    results: tuple[Path, ...]


@dataclass(frozen=True)
class WorkloadMatch:
    recipe_path: Path
    workload_name: str
    configs: tuple[ConfigMatch, ...]
    accuracy_tasks: tuple[AccuracyMatch, ...]


@dataclass(frozen=True)
class DiscoveryReport:
    workloads: tuple[WorkloadMatch, ...]
    unmatched_results: tuple[Path, ...]
    invalid_files: tuple[tuple[Path, str], ...]

    @property
    def config_count(self) -> int:
        return sum(len(workload.configs) for workload in self.workloads)

    @property
    def accuracy_count(self) -> int:
        return len(
            {
                result
                for workload in self.workloads
                for task in workload.accuracy_tasks
                for result in task.results
            }
        )

    @property
    def result_count(self) -> int:
        return len(
            {
                result
                for workload in self.workloads
                for match in (*workload.configs, *workload.accuracy_tasks)
                for result in match.results
            }
        )


def yaml_files(root: Path) -> tuple[Path, ...]:
    return tuple(sorted((*root.rglob("*.yaml"), *root.rglob("*.yml"))))


def json_files(root: Path) -> tuple[Path, ...]:
    return tuple(sorted(root.rglob("*.json")))


def config_identity(config: dict[str, Any]) -> tuple[object, object]:
    return config.get("max_concurrency"), config.get("num_prompts")


def accuracy_tasks(recipe: dict[str, Any]) -> tuple[str, ...]:
    lm_eval = recipe.get("lm_eval")
    if lm_eval is None:
        return ()
    if not isinstance(lm_eval, dict):
        raise ValueError("lm_eval must be a mapping")
    tasks = lm_eval.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("lm_eval tasks must be a non-empty list")
    names = []
    for task in tasks:
        if isinstance(task, str):
            name = task
        elif isinstance(task, dict):
            name = task.get("name")
        else:
            raise ValueError("lm_eval task must be a name or mapping")
        if not isinstance(name, str) or not name:
            raise ValueError("lm_eval task must have a name")
        names.append(name)
    return tuple(names)


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
    recipes: list[tuple[Path, dict[str, Any], tuple[str, ...]]] = []
    for path in yaml_files(workloads_dir):
        try:
            recipe = load_mapping(path)
            if not recipe.get("name"):
                continue
            configs = recipe.get("vllm_bench", {}).get("configs")
            tasks = accuracy_tasks(recipe)
            if not configs and not tasks:
                continue
            if configs:
                expand_bench_configs(recipe)
            recipes.append((path, recipe, tasks))
        except (OSError, ValueError, TypeError) as error:
            invalid.append((path, str(error)))

    performance_results: list[tuple[Path, dict[str, Any]]] = []
    accuracy_results: list[tuple[Path, dict[str, Any]]] = []
    for path in json_files(results_dir):
        try:
            result = load_mapping(path)
            if "max_concurrency" in result or "num_prompts" in result:
                if "max_concurrency" not in result or "num_prompts" not in result:
                    raise ValueError(
                        "benchmark result must contain max_concurrency and num_prompts"
                    )
                performance_results.append((path, result))
            elif "results" in result:
                if not isinstance(result["results"], dict):
                    raise ValueError("lm-eval results must be a mapping")
                accuracy_results.append((path, result))
        except (OSError, ValueError, TypeError) as error:
            invalid.append((path, str(error)))

    claimed: set[Path] = set()
    workloads: list[WorkloadMatch] = []
    recipe_paths = tuple(path for path, _, _ in recipes)
    for recipe_path, recipe, tasks in recipes:
        workload_name = str(recipe["name"])
        scoped_performance = result_scope(
            recipe_path,
            workload_name,
            results_dir,
            performance_results,
            recipe_paths,
        )
        config_matches = []
        for config in (
            expand_bench_configs(recipe) if recipe.get("vllm_bench", {}).get("configs") else ()
        ):
            identity = config_identity(config)
            candidates = []
            for result_path, result in scoped_performance:
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

        scoped_accuracy = result_scope(
            recipe_path,
            workload_name,
            results_dir,
            accuracy_results,
            recipe_paths,
        )
        accuracy_matches = []
        for task in sorted(tasks):
            candidates = tuple(
                sorted(
                    result_path
                    for result_path, result in scoped_accuracy
                    if isinstance(result["results"].get(task), dict)
                )
            )
            accuracy_matches.append(AccuracyMatch(task_name=task, results=candidates))
            claimed.update(candidates)
        workloads.append(
            WorkloadMatch(
                recipe_path=recipe_path,
                workload_name=workload_name,
                configs=tuple(config_matches),
                accuracy_tasks=tuple(accuracy_matches),
            )
        )

    parsed_results = (*performance_results, *accuracy_results)
    return DiscoveryReport(
        workloads=tuple(workloads),
        unmatched_results=tuple(path for path, _ in parsed_results if path not in claimed),
        invalid_files=tuple(sorted(invalid, key=lambda item: item[0])),
    )
