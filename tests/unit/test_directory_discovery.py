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
