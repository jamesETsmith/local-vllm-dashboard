from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from local_vllm_dashboard.artifacts import ArtifactContent
from local_vllm_dashboard.contracts import Bundle
from local_vllm_dashboard.db.models import (
    ArtifactRecord,
    BundleRecord,
    DependencyRevisionRecord,
    MetricRecord,
    ObservationRecord,
)
from local_vllm_dashboard.db.schema import dependency_commits


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

    def save(
        self,
        bundle: Bundle,
        artifacts: tuple[ArtifactContent, ...] = (),
    ) -> SaveResult:
        existing = self.session.scalar(
            select(BundleRecord).where(BundleRecord.idempotency_key == bundle.idempotency_key)
        )
        if existing is not None:
            return SaveResult(existing.bundle_id, SaveStatus.DUPLICATE)

        record = BundleRecord(
            bundle_id=bundle.bundle_id,
            idempotency_key=bundle.idempotency_key,
            schema_version=bundle.schema_version,
            accepted_at=datetime.now(UTC),
            payload=bundle.model_dump(mode="json"),
            dependency_revisions=[
                DependencyRevisionRecord(name=name, revision=revision)
                for name, revision in dependency_commits(bundle.model_dump(mode="json"))
            ],
            artifacts=[
                ArtifactRecord(
                    path=declaration.path,
                    role=declaration.role,
                    media_type=artifact.media_type,
                    size_bytes=declaration.size_bytes,
                    digest=declaration.digest,
                    content=artifact.content,
                )
                for declaration in bundle.run.source.artifacts
                for artifact in artifacts
                if Path(artifact.path).name == Path(declaration.path).name
                and artifact.role == declaration.role
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
            if existing is None:
                raise
            return SaveResult(existing.bundle_id, SaveStatus.DUPLICATE)
        return SaveResult(bundle.bundle_id, SaveStatus.ACCEPTED)
