from pathlib import Path

import httpx
import pytest

from local_vllm_dashboard.artifacts import ArtifactContent
from local_vllm_dashboard.contracts import Bundle
from local_vllm_dashboard.publisher import Publisher

FIXTURE = Path(__file__).parents[1] / "fixtures" / "contracts" / "v1" / "performance.json"


def load_bundle() -> Bundle:
    return Bundle.model_validate_json(FIXTURE.read_text())


def test_publisher_sends_one_request_with_idempotency_header() -> None:
    bundle = load_bundle()
    bundle = bundle.model_copy(update={"idempotency_key": bundle.calculated_idempotency_key()})
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"bundle_id": str(bundle.bundle_id), "status": "accepted"})

    publisher = Publisher("http://results.internal")
    publisher.client.close()
    publisher.client = httpx.Client(transport=httpx.MockTransport(handle))

    artifact = ArtifactContent(
        path="result.json",
        role="raw_bench_result",
        media_type="application/json",
        content=b"{}",
    )
    result = publisher.publish(bundle, (artifact,))

    assert result.status == "accepted"
    assert len(requests) == 1
    assert requests[0].url.path == "/v1/bundles"
    assert requests[0].headers["Idempotency-Key"] == bundle.idempotency_key
    assert requests[0].headers["content-type"].startswith("multipart/form-data")
    assert b"X-Artifact-Role: raw_bench_result" in requests[0].content
    assert b'name="bundle"' in requests[0].content


def test_publisher_rejects_mismatched_idempotency_key() -> None:
    bundle = load_bundle()

    with Publisher("http://results.internal") as publisher:
        with pytest.raises(ValueError, match="idempotency key"):
            publisher.publish(bundle)
