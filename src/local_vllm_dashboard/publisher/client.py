from __future__ import annotations

from dataclasses import dataclass

import httpx

from local_vllm_dashboard.artifacts import ArtifactContent
from local_vllm_dashboard.contracts import Bundle


@dataclass(frozen=True)
class PublishResult:
    bundle_id: str
    status: str


class Publisher:
    def __init__(
        self,
        endpoint: str,
        *,
        token: str,
        timeout: float = 30,
        retries: int = 2,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        transport = httpx.HTTPTransport(retries=retries)
        self.client = httpx.Client(transport=transport, timeout=timeout)

    def publish(
        self,
        bundle: Bundle,
        artifacts: tuple[ArtifactContent, ...] = (),
    ) -> PublishResult:
        if not bundle.has_valid_idempotency_key():
            raise ValueError("bundle idempotency key does not match its canonical content")
        files = [
            ("bundle", ("bundle.json", bundle.canonical_json(), "application/json")),
            *[
                (
                    "artifacts",
                    (
                        artifact.path,
                        artifact.content,
                        artifact.media_type,
                        {"X-Artifact-Role": artifact.role},
                    ),
                )
                for artifact in artifacts
            ],
        ]
        response = self.client.post(
            f"{self.endpoint}/v1/bundles",
            files=files,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Idempotency-Key": bundle.idempotency_key,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return PublishResult(bundle_id=str(payload["bundle_id"]), status=str(payload["status"]))

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> Publisher:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
