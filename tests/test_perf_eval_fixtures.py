import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "perf_eval"


def test_failed_benchmark_fixture_preserves_failure_state() -> None:
    result = json.loads((FIXTURES / "glm_5_2_mxfp4_mi355x_failed_bench.json").read_text())

    assert result["model_id"] == "amd/GLM-5.2-MXFP4"
    assert result["num_prompts"] == 40
    assert result["completed"] == 0
    assert result["failed"] == 40
