from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from local_vllm_dashboard.api import Settings, create_app
from local_vllm_dashboard.contracts import Bundle
from local_vllm_dashboard.db import Base, make_session_factory
from local_vllm_dashboard.db.models import BundleRecord

FIXTURE = Path(__file__).parents[1] / "fixtures" / "contracts" / "v1" / "performance.json"


def valid_bundle() -> Bundle:
    bundle = Bundle.model_validate_json(FIXTURE.read_text())
    return bundle.model_copy(update={"idempotency_key": bundle.calculated_idempotency_key()})


def memory_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_ingestion_accepts_then_deduplicates_one_way_submission() -> None:
    engine = memory_engine()
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"), factory)
    bundle = valid_bundle()

    with TestClient(app) as client:
        accepted = client.post(
            "/v1/bundles",
            content=bundle.canonical_json(),
            headers={"Idempotency-Key": bundle.idempotency_key},
        )
        duplicate = client.post(
            "/v1/bundles",
            content=bundle.canonical_json(),
            headers={"Idempotency-Key": bundle.idempotency_key},
        )

    assert accepted.status_code == 201
    assert accepted.json()["status"] == "accepted"
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(BundleRecord)) == 1


def test_ingestion_rejects_header_mismatch() -> None:
    engine = memory_engine()
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"), factory)
    bundle = valid_bundle()

    with TestClient(app) as client:
        response = client.post(
            "/v1/bundles",
            content=bundle.canonical_json(),
            headers={"Idempotency-Key": f"sha256:{'f' * 64}"},
        )

    assert response.status_code == 409


def test_ingestion_rejects_large_request() -> None:
    engine = memory_engine()
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", max_request_bytes=10)
    app = create_app(settings, factory)
    bundle = valid_bundle()

    with TestClient(app) as client:
        response = client.post(
            "/v1/bundles",
            content=bundle.canonical_json(),
            headers={"Idempotency-Key": bundle.idempotency_key},
        )

    assert response.status_code == 413
