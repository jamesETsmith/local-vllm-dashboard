import json
import tarfile
from pathlib import Path

import yaml

from local_vllm_dashboard.adapter import build_performance_bundle
from local_vllm_dashboard.container_revisions import ContainerRevisions
from local_vllm_dashboard.package_results import create_results_archive


def test_archive_preserves_results_and_runtime_revisions(tmp_path: Path) -> None:
    workloads = tmp_path / "workloads"
    results = tmp_path / "results"
    recipe_path = workloads / "nested" / "demo.yaml"
    result_path = results / "demo" / "bench.json"
    recipe_path.parent.mkdir(parents=True)
    result_path.parent.mkdir(parents=True)
    recipe_path.write_text(
        yaml.safe_dump(
            {
                "name": "demo",
                "gpu": "MI355X",
                "num_gpus": 1,
                "vllm": {"model": "example/model", "image": "example/image"},
                "vllm_bench": {
                    "metadata": {"tp": 1, "precision": "fp8"},
                    "configs": [
                        {
                            "name": "conc-2",
                            "backend": "openai",
                            "dataset": "random",
                            "input_len": 10,
                            "output_len": 5,
                            "num_prompts": 2,
                            "max_concurrency": 2,
                        }
                    ],
                },
            },
            sort_keys=False,
        )
    )
    result_path.write_text(
        json.dumps(
            {
                "date": "20260725-120000",
                "model_id": "example/model",
                "num_prompts": 2,
                "max_concurrency": 2,
                "duration": 1,
                "completed": 2,
                "failed": 0,
                "request_throughput": 1,
                "output_throughput": 2,
                "total_token_throughput": 3,
            }
        )
    )
    output = tmp_path / "upload.tar.gz"

    _, summary = create_results_archive(
        workloads,
        results,
        output,
        revision_overrides={
            recipe_path: ContainerRevisions(
                container="perf-eval-demo-123",
                vllm_commit="abcdef0",
                aiter_commit="fedcba0",
            )
        },
    )

    assert summary.workloads == 1
    assert summary.results == 1
    assert summary.revisions == 1
    with tarfile.open(output, mode="r:gz") as archive:
        assert archive.getnames() == [
            "workloads/nested/demo.yaml",
            "workloads/nested/demo.revisions.json",
            "results/demo/bench.json",
        ]
        archive.extractall(tmp_path / "extracted", filter="data")
    bundle = build_performance_bundle(
        tmp_path / "extracted/workloads/nested/demo.yaml",
        tmp_path / "extracted/results/demo/bench.json",
    )
    assert bundle.run.vllm.commit == "abcdef0"
    assert bundle.environment.extensions["aiter_commit"] == "fedcba0"
    assert bundle.run.source.extensions["container"] == "perf-eval-demo-123"
