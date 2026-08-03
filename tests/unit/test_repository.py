from pathlib import Path

from sqlalchemy import func, insert, select
from sqlalchemy.sql.schema import Table

from local_vllm_dashboard.contracts import Bundle
from local_vllm_dashboard.db import (
    Base,
    BundleRepository,
    SaveStatus,
    initialize_schema,
    make_engine,
    make_session_factory,
)
from local_vllm_dashboard.db.models import (
    BundleRecord,
    DependencyRevisionRecord,
    MetricRecord,
    ObservationRecord,
)

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


def test_repository_persists_dependency_commits() -> None:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    bundle = valid_bundle()
    environment = bundle.environment.model_copy(
        update={"extensions": {"aiter_commit": "fedcba0", "expert_parallel": True}}
    )
    updated = bundle.model_copy(update={"environment": environment})
    updated = updated.model_copy(update={"idempotency_key": updated.calculated_idempotency_key()})

    with factory() as session:
        BundleRepository(session).save(updated)
        revisions = session.scalars(select(DependencyRevisionRecord)).all()

        assert [(revision.name, revision.revision) for revision in revisions] == [
            ("aiter_commit", "fedcba0")
        ]


def test_schema_initialization_backfills_dependency_commits() -> None:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    bundles_table = BundleRecord.metadata.tables[BundleRecord.__tablename__]
    assert isinstance(bundles_table, Table)
    BundleRecord.metadata.create_all(engine, tables=[bundles_table])
    bundle = valid_bundle()
    environment = bundle.environment.model_copy(update={"extensions": {"aiter_commit": "fedcba0"}})
    updated = bundle.model_copy(update={"environment": environment})
    with engine.begin() as connection:
        connection.execute(
            insert(BundleRecord).values(
                bundle_id=updated.bundle_id,
                idempotency_key=updated.calculated_idempotency_key(),
                schema_version=updated.schema_version,
                accepted_at=updated.run.completed_at,
                payload=updated.model_dump(mode="json"),
            )
        )

    initialize_schema(engine)

    factory = make_session_factory(engine)
    with factory() as session:
        revision = session.scalar(select(DependencyRevisionRecord))
        assert revision is not None
        assert (revision.name, revision.revision) == ("aiter_commit", "fedcba0")


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


def test_repository_deduplicates_semantically_identical_payload() -> None:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    bundle = valid_bundle()
    conflict = bundle.model_copy(update={"labels": {"branch": "other"}})

    with factory() as session:
        repository = BundleRepository(session)
        repository.save(bundle)
        result = repository.save(conflict)

        assert result.status == SaveStatus.DUPLICATE
        assert result.bundle_id == bundle.bundle_id
