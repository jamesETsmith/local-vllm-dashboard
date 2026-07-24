from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from local_vllm_dashboard.contracts import Bundle
from local_vllm_dashboard.db.models import (
    ArtifactRecord,
    BundleRecord,
    MetricRecord,
    ObservationRecord,
)


class SaveStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class SaveResult:
    bundle_id: UUID
    status: SaveStatus


class IdempotencyConflictError(Exception):
    pass


class BundleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, bundle: Bundle) -> SaveResult:
        existing = self.session.scalar(
            select(BundleRecord).where(BundleRecord.idempotency_key == bundle.idempotency_key)
        )
        if existing is not None:
            if existing.payload != bundle.model_dump(mode="json"):
                raise IdempotencyConflictError("idempotency key is already used by another payload")
            return SaveResult(existing.bundle_id, SaveStatus.DUPLICATE)

        record = BundleRecord(
            bundle_id=bundle.bundle_id,
            idempotency_key=bundle.idempotency_key,
            schema_version=bundle.schema_version,
            accepted_at=datetime.now(UTC),
            payload=bundle.model_dump(mode="json"),
            artifacts=[
                ArtifactRecord(
                    path=artifact.path,
                    role=artifact.role,
                    size_bytes=artifact.size_bytes,
                    digest=artifact.digest,
                )
                for artifact in bundle.run.source.artifacts
            ],
            observations=[
                ObservationRecord(
                    observation_id=observation.observation_id,
                    kind=observation.kind,
                    subject=observation.subject,
                    configuration=observation.configuration,
                    source=observation.source.model_dump(mode="json"),
                    metrics=[
                        MetricRecord(
                            name=metric.name,
                            value=metric.value,
                            unit=metric.unit,
                            aggregation=metric.aggregation,
                        )
                        for metric in observation.metrics
                    ],
                )
                for observation in bundle.observations
            ],
        )
        self.session.add(record)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.session.scalar(
                select(BundleRecord).where(BundleRecord.idempotency_key == bundle.idempotency_key)
            )
            if existing is None or existing.payload != bundle.model_dump(mode="json"):
                raise
            return SaveResult(existing.bundle_id, SaveStatus.DUPLICATE)
        return SaveResult(bundle.bundle_id, SaveStatus.ACCEPTED)
