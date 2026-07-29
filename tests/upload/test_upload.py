import io
import json
import tarfile
from pathlib import Path

import pytest

from local_vllm_dashboard.upload import UploadedFile, archive_files, stage_upload


def make_archive(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_archive_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="unsafe path"):
        archive_files(make_archive({"../secret.yaml": b"name: bad"}))


def test_archive_ignores_unrelated_regular_files() -> None:
    files = archive_files(
        make_archive(
            {
                "workloads/demo.yaml": b"name: demo",
                "notes/readme.txt": b"not benchmark data",
            }
        )
    )

    assert [item.path for item in files] == ["workloads/demo.yaml"]


def test_archive_rejects_links() -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo("link.yaml")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        archive.addfile(info)
    with pytest.raises(ValueError, match="unsupported archive member"):
        archive_files(buffer.getvalue())


def test_stage_upload_discovers_workload_and_result(tmp_path: Path) -> None:
    recipe = b"""name: demo
gpu: MI355X
num_gpus: 1
vllm:
  model: example/model
  image: example/image
vllm_bench:
  metadata: {tp: 1, precision: fp8}
  configs:
    - name: conc-2
      backend: openai
      dataset: random
      input_len: 10
      output_len: 5
      num_prompts: 2
      max_concurrency: 2
"""
    result = json.dumps(
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
    ).encode()

    preview = stage_upload(
        (
            UploadedFile("workloads/demo.yaml", recipe),
            UploadedFile("results/demo/bench-conc-2.json", result),
        ),
        tmp_path,
    )

    assert preview.report.config_count == 1
    assert preview.report.result_count == 1
