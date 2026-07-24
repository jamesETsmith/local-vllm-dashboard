from pathlib import Path

import pytest
from sqlalchemy import func, select

from local_vllm_dashboard.contracts import Bundle
from local_vllm_dashboard.db import (
    Base,
    BundleRepository,
    SaveStatus,
    make_engine,
    make_session_factory,
)
from local_vllm_dashboard.db.models import BundleRecord, MetricRecord, ObservationRecord
from local_vllm_dashboard.db.repository import IdempotencyConflictError

FIXTURE = Path(__file__).parents[1] / "fixtures" / "contracts" / "v1" / "performance.json"


def valid_bundle() -> Bundle:
    bundle = Bundle.model_validate_json(FIXTURE.read_text())
    return bundle.model_copy(update={"idempotency_key": bundle.calculated_idempotency_key()})


def test_repository_persists_normalized_bundle_atomically() -> None:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)

    with factory() as session:
        result = BundleRepository(session).save(valid_bundle())
        assert result.status == SaveStatus.ACCEPTED
        assert session.scalar(select(func.count()).select_from(BundleRecord)) == 1
        assert session.scalar(select(func.count()).select_from(ObservationRecord)) == 1
        assert session.scalar(select(func.count()).select_from(MetricRecord)) == 2


def test_repository_returns_duplicate_for_same_payload() -> None:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    bundle = valid_bundle()

    with factory() as session:
        repository = BundleRepository(session)
        repository.save(bundle)
        duplicate = repository.save(bundle)

        assert duplicate.status == SaveStatus.DUPLICATE
        assert session.scalar(select(func.count()).select_from(BundleRecord)) == 1


def test_repository_rejects_key_reuse_for_different_payload() -> None:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    bundle = valid_bundle()
    conflict = bundle.model_copy(update={"labels": {"branch": "other"}})

    with factory() as session:
        repository = BundleRepository(session)
        repository.save(bundle)
        with pytest.raises(IdempotencyConflictError):
            repository.save(conflict)
