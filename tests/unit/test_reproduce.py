import json
from pathlib import Path

import httpx
import pytest

from local_vllm_dashboard.reproduce import (
    fetch_reproduction,
    render_reproduction,
    reproduction_files,
    write_reproduction,
)

PAYLOAD = {
    "run": {
        "bundle_id": "018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1a",
        "workload": "prefix-cache-performance-mi355x",
        "model": "example-org/example-model",
        "hardware": "MI355X",
        "completed_at": "2026-07-23T14:16:48Z",
        "vllm_image": "example-registry/vllm-openai:test",
        "vllm_commit": "abcdef0",
        "dependency_revisions": [["aiter", "fedcba0"]],
    },
    "perf_eval_command": "./lib/run.sh prefix_cache_workload.yaml",
    "recipes": [
        {
            "observation_id": "50k-in-1k-out-40k-cached-conc-4",
            "server_command": "docker run --rm image",
            "benchmark_command": "vllm bench serve --model example-org/example-model",
        }
    ],
    "artifacts": [
        {
            "path": "prefix_cache_workload.yaml",
            "role": "workload_recipe",
            "media_type": "application/yaml",
            "size_bytes": 12,
            "digest": "sha256:abc",
            "content": "name: example\n",
        },
        {
            "path": "bench.json",
            "role": "raw_bench_result",
            "media_type": "application/json",
            "size_bytes": 2,
            "digest": "sha256:def",
            "content": "{}",
        },
    ],
}


def reproduction_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(
            "/api/v1/configurations/018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1a/reproduction"
        )
        return httpx.Response(200, json=PAYLOAD)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_reproduction_parses_stored_artifacts_and_commands() -> None:
    with reproduction_client() as client:
        reproduction = fetch_reproduction(
            "http://192.0.2.10:8010",
            "018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1a",
            client=client,
        )

    assert reproduction.workload == "prefix-cache-performance-mi355x"
    assert reproduction.vllm_commit == "abcdef0"
    assert reproduction.dependency_revisions == (("aiter", "fedcba0"),)
    assert reproduction.perf_eval_command == "./lib/run.sh prefix_cache_workload.yaml"
    assert reproduction.workload_recipe is not None
    assert reproduction.workload_recipe.content == "name: example\n"
    assert [artifact.path for artifact in reproduction.result_artifacts] == ["bench.json"]
    assert reproduction.recipes[0].benchmark_command.startswith("vllm bench serve")


def test_fetch_reproduction_reports_missing_bundle() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "bundle not found"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SystemExit, match="bundle not found"):
            fetch_reproduction("http://192.0.2.10:8010", "missing", client=client)


def test_write_reproduction_persists_artifacts_and_summary(tmp_path: Path) -> None:
    with reproduction_client() as client:
        reproduction = fetch_reproduction(
            "http://192.0.2.10:8010",
            "018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1a",
            client=client,
        )

    written = write_reproduction(reproduction, tmp_path)

    assert (tmp_path / "prefix_cache_workload.yaml").read_text() == "name: example\n"
    assert (tmp_path / "bench.json").read_text() == "{}"
    summary = json.loads((tmp_path / "reproduction.json").read_text())
    assert summary["bundle_id"] == reproduction.bundle_id
    assert summary["dependency_revisions"] == [["aiter", "fedcba0"]]
    assert summary["recipes"][0]["server_command"] == "docker run --rm image"
    assert set(written) == {
        tmp_path / "prefix_cache_workload.yaml",
        tmp_path / "bench.json",
        tmp_path / "reproduction.json",
    }
    assert set(reproduction_files(reproduction)) == {
        "prefix_cache_workload.yaml",
        "bench.json",
        "reproduction.json",
    }


def test_render_reproduction_describes_perf_eval_workflow(tmp_path: Path) -> None:
    with reproduction_client() as client:
        reproduction = fetch_reproduction(
            "http://192.0.2.10:8010",
            "018f4d6a-4c1f-7c7a-98cf-3b5c7cef3d1a",
            client=client,
        )

    rendered = render_reproduction(reproduction, tmp_path)

    assert "git clone https://github.com/vllm-project/perf-eval" in rendered
    assert "./lib/run.sh prefix_cache_workload.yaml" in rendered
    assert "docker run --rm image" in rendered
    assert "vllm bench serve --model example-org/example-model" in rendered
    assert "AITER commit: fedcba0" in rendered
