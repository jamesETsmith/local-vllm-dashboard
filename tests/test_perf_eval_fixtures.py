import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "perf_eval"


def test_partial_failure_fixture_preserves_measurements() -> None:
    result = json.loads((FIXTURES / "prefix_cache_partial_failure_bench.json").read_text())

    assert result["model_id"] == "example-org/example-model"
    assert result["num_prompts"] == 40
    assert result["completed"] == 1
    assert result["failed"] == 39
    assert result["total_input_tokens"] == 50000
    assert result["total_token_throughput"] == 2956.63758420712
