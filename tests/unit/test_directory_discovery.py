import json
from pathlib import Path

import yaml

from local_vllm_dashboard.adapter import discover
from local_vllm_dashboard.ingest_directory import render_report


def recipe(name: str, configs: list[tuple[str, int, int]]) -> dict:
    return {
        "name": name,
        "gpu": "MI355X",
        "num_gpus": 4,
        "vllm": {"model": "example/model", "image": "example/image"},
        "vllm_bench": {
            "metadata": {"tp": 4, "precision": "fp8"},
            "configs": [
                {
                    "name": config_name,
                    "backend": "openai",
                    "dataset": "random",
                    "input_len": 1000,
                    "output_len": 100,
                    "num_prompts": prompts,
                    "max_concurrency": concurrency,
                }
                for config_name, concurrency, prompts in configs
            ],
        },
    }


def result(concurrency: int, prompts: int) -> dict:
    return {
        "date": "20260725-120000",
        "model_id": "example/model",
        "num_prompts": prompts,
        "max_concurrency": concurrency,
        "duration": 1,
        "completed": prompts,
        "failed": 0,
        "request_throughput": 1,
        "output_throughput": 2,
        "total_token_throughput": 3,
    }


def write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_discovery_reports_repeated_missing_and_unmatched_results(tmp_path: Path) -> None:
    workloads = tmp_path / "workloads"
    results = tmp_path / "results"
    write_yaml(
        workloads / "example.yaml",
        recipe("example-run", [("conc-2", 2, 20), ("conc-4", 4, 40)]),
    )
    write_json(results / "example-run" / "attempt-1" / "bench.json", result(2, 20))
    write_json(results / "example-run" / "attempt-2" / "bench.json", result(2, 20))
    write_json(results / "other" / "bench.json", result(8, 80))

    report = discover(workloads, results)
    rendered = render_report(report, workloads, results)

    assert report.config_count == 2
    assert report.result_count == 2
    assert len(report.workloads[0].configs[0].results) == 2
    assert not report.workloads[0].configs[1].results
    assert report.unmatched_results == (results / "other" / "bench.json",)
    assert "REPEATED conc-2 (2 results)" in rendered
    assert "MISSING  conc-4" in rendered
    assert "Unmatched results (1)" in rendered


def test_discovery_pairs_flat_attempt_files_by_recipe_stem(tmp_path: Path) -> None:
    workloads = tmp_path / "workloads"
    results = tmp_path / "results"
    write_yaml(workloads / "conc-2-workload.yml", recipe("attempt-1", [("conc-2", 2, 20)]))
    write_yaml(
        workloads / "conc-2-attempt-02-workload.yml",
        recipe("attempt-2", [("conc-2", 2, 20)]),
    )
    write_json(results / "conc-2-bench.json", result(2, 20))
    write_json(results / "conc-2-attempt-02-bench.json", result(2, 20))

    report = discover(workloads, results)

    assert report.result_count == 2
    assert report.workloads[0].configs[0].results == (results / "conc-2-attempt-02-bench.json",)
    assert report.workloads[1].configs[0].results == (results / "conc-2-bench.json",)


def test_discovery_does_not_assign_later_attempt_to_missing_first_attempt(
    tmp_path: Path,
) -> None:
    workloads = tmp_path / "workloads"
    results = tmp_path / "results"
    write_yaml(
        workloads / "conc-4-workload.yml",
        recipe("attempt-1", [("conc-4", 4, 40)]),
    )
    write_yaml(
        workloads / "conc-4-attempt-02-workload.yml",
        recipe("attempt-2", [("conc-4", 4, 40)]),
    )
    write_json(results / "conc-4-attempt-02-bench.json", result(4, 40))

    report = discover(workloads, results)

    assert report.result_count == 1
    assert report.workloads[0].configs[0].results == (results / "conc-4-attempt-02-bench.json",)
    assert not report.workloads[1].configs[0].results


def test_discovery_supports_flat_export_directories(tmp_path: Path) -> None:
    workloads = tmp_path / "workloads"
    results = tmp_path / "results"
    write_yaml(workloads / "example.yaml", recipe("example-run", [("conc-2", 2, 20)]))
    write_json(results / "exported-result.json", result(2, 20))

    report = discover(workloads, results)

    assert report.result_count == 1
    assert report.workloads[0].configs[0].results == (results / "exported-result.json",)


def test_discovery_expands_paired_concurrency_and_prompt_sweeps(tmp_path: Path) -> None:
    workloads = tmp_path / "workloads"
    results = tmp_path / "results"
    sweep_recipe = recipe("example-run", [("sweep", 1, 10)])
    sweep_config = sweep_recipe["vllm_bench"]["configs"][0]
    sweep_config["max_concurrency"] = [1, 2, 4]
    sweep_config["num_prompts"] = [10, 20, 40]
    write_yaml(workloads / "example.yaml", sweep_recipe)
    for concurrency, prompts in ((1, 10), (2, 20), (4, 40)):
        write_json(
            results / "example-run" / f"conc-{concurrency}.json",
            result(concurrency, prompts),
        )

    report = discover(workloads, results)

    assert report.config_count == 3
    assert report.result_count == 3
    assert [match.results for match in report.workloads[0].configs] == [
        (results / "example-run" / "conc-1.json",),
        (results / "example-run" / "conc-2.json",),
        (results / "example-run" / "conc-4.json",),
    ]
    assert not report.unmatched_results


def test_discovery_rejects_incompatible_sweep_lengths(tmp_path: Path) -> None:
    workloads = tmp_path / "workloads"
    results = tmp_path / "results"
    sweep_recipe = recipe("example-run", [("sweep", 1, 10)])
    sweep_config = sweep_recipe["vllm_bench"]["configs"][0]
    sweep_config["max_concurrency"] = [1, 2]
    sweep_config["num_prompts"] = [10]
    recipe_path = workloads / "example.yaml"
    write_yaml(recipe_path, sweep_recipe)

    report = discover(workloads, results)

    assert not report.workloads
    assert report.invalid_files == (
        (recipe_path, "max_concurrency and num_prompts arrays must have equal lengths"),
    )


def test_discovery_rejects_mixed_sweep_and_scalar_values(tmp_path: Path) -> None:
    workloads = tmp_path / "workloads"
    results = tmp_path / "results"
    sweep_recipe = recipe("example-run", [("sweep", 1, 10)])
    sweep_config = sweep_recipe["vllm_bench"]["configs"][0]
    sweep_config["max_concurrency"] = [1, 2]
    recipe_path = workloads / "example.yaml"
    write_yaml(recipe_path, sweep_recipe)

    report = discover(workloads, results)

    assert not report.workloads
    assert report.invalid_files == (
        (recipe_path, "max_concurrency and num_prompts must both be arrays or scalars"),
    )


def test_discovery_matches_nested_accuracy_results_by_declared_task(tmp_path: Path) -> None:
    workloads = tmp_path / "workloads"
    results = tmp_path / "results"
    accuracy_recipe = recipe("mixed-run", [("conc-2", 2, 20)])
    accuracy_recipe["lm_eval"] = {
        "tasks": [{"name": "gsm8k", "num_fewshot": 5}, {"name": "arc_easy"}]
    }
    recipe_path = workloads / "mixed.yaml"
    accuracy_path = results / "mixed-run" / "gsm8k" / "results_2026.json"
    unmatched_path = results / "other" / "results_2026.json"
    write_yaml(recipe_path, accuracy_recipe)
    write_json(
        accuracy_path,
        {
            "results": {"gsm8k": {"exact_match": 0.742}},
            "configs": {"gsm8k": {"num_fewshot": 5}},
        },
    )
    write_json(unmatched_path, {"results": {"mmlu": {"acc": 0.5}}})

    report = discover(workloads, results)
    rendered = render_report(report, workloads, results)

    assert report.accuracy_count == 1
    assert report.workloads[0].accuracy_tasks[0].task_name == "arc_easy"
    assert not report.workloads[0].accuracy_tasks[0].results
    assert report.workloads[0].accuracy_tasks[1].task_name == "gsm8k"
    assert report.workloads[0].accuracy_tasks[1].results == (accuracy_path,)
    assert report.unmatched_results == (unmatched_path,)
    assert "MISSING  lm-eval:arc_easy" in rendered
    assert "MATCHED  lm-eval:gsm8k -> mixed-run/gsm8k/results_2026.json" in rendered


def test_discovery_reports_invalid_accuracy_recipe_and_result(tmp_path: Path) -> None:
    workloads = tmp_path / "workloads"
    results = tmp_path / "results"
    invalid_recipe = recipe("invalid-run", [("conc-2", 2, 20)])
    invalid_recipe["lm_eval"] = {"tasks": [{"num_fewshot": 5}]}
    recipe_path = workloads / "invalid.yaml"
    result_path = results / "invalid-run" / "results.json"
    write_yaml(recipe_path, invalid_recipe)
    write_json(result_path, {"results": []})

    report = discover(workloads, results)

    assert not report.workloads
    assert report.invalid_files == tuple(
        sorted(
            (
                (recipe_path, "lm_eval task must have a name"),
                (result_path, "lm-eval results must be a mapping"),
            ),
            key=lambda item: item[0],
        )
    )
