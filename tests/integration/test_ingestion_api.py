from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from local_vllm_dashboard.api import Settings, create_app
from local_vllm_dashboard.artifacts import ArtifactContent
from local_vllm_dashboard.contracts import Bundle
from local_vllm_dashboard.db import Base, make_session_factory
from local_vllm_dashboard.db.models import ArtifactRecord, BundleRecord

FIXTURE = Path(__file__).parents[1] / "fixtures" / "contracts" / "v1" / "performance.json"


def valid_bundle() -> Bundle:
    bundle = Bundle.model_validate_json(FIXTURE.read_text())
    return bundle.model_copy(update={"idempotency_key": bundle.calculated_idempotency_key()})


def declared_artifacts(bundle: Bundle) -> tuple[ArtifactContent, ...]:
    return tuple(
        ArtifactContent(
            path=declaration.path,
            role=declaration.role,
            media_type=(
                "application/json" if declaration.path.endswith(".json") else "application/yaml"
            ),
            content=(b"a" * declaration.size_bytes),
        )
        for declaration in bundle.run.source.artifacts
    )


def matching_bundle() -> tuple[Bundle, tuple[ArtifactContent, ...]]:
    bundle = valid_bundle()
    artifacts = declared_artifacts(bundle)
    declarations = tuple(
        declaration.model_copy(
            update={
                "size_bytes": len(artifact.content),
                "digest": f"sha256:{__import__('hashlib').sha256(artifact.content).hexdigest()}",
            }
        )
        for declaration, artifact in zip(bundle.run.source.artifacts, artifacts, strict=True)
    )
    source = bundle.run.source.model_copy(update={"artifacts": declarations})
    run = bundle.run.model_copy(update={"source": source})
    updated = bundle.model_copy(update={"run": run})
    updated = updated.model_copy(update={"idempotency_key": updated.calculated_idempotency_key()})
    return updated, artifacts


def multipart(bundle: Bundle, artifacts: tuple[ArtifactContent, ...]) -> list[tuple[str, tuple]]:
    return [
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
    bundle, artifacts = matching_bundle()

    with TestClient(app) as client:
        accepted = client.post(
            "/v1/bundles",
            files=multipart(bundle, artifacts),
            headers={"Idempotency-Key": bundle.idempotency_key},
        )
        duplicate = client.post(
            "/v1/bundles",
            files=multipart(bundle, artifacts),
            headers={"Idempotency-Key": bundle.idempotency_key},
        )

    assert accepted.status_code == 201
    assert accepted.json()["status"] == "accepted"
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(BundleRecord)) == 1
        assert session.scalar(select(func.count()).select_from(ArtifactRecord)) == len(artifacts)


def test_ingestion_rejects_header_mismatch() -> None:
    engine = memory_engine()
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"), factory)
    bundle, artifacts = matching_bundle()

    with TestClient(app) as client:
        response = client.post(
            "/v1/bundles",
            files=multipart(bundle, artifacts),
            headers={"Idempotency-Key": f"sha256:{'f' * 64}"},
        )

    assert response.status_code == 409


def test_ingestion_rejects_missing_or_changed_artifact() -> None:
    engine = memory_engine()
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"), factory)
    bundle, artifacts = matching_bundle()

    with TestClient(app) as client:
        missing = client.post(
            "/v1/bundles",
            files=multipart(bundle, artifacts[:-1]),
            headers={"Idempotency-Key": bundle.idempotency_key},
        )
        changed = artifacts[0].__class__(
            path=artifacts[0].path,
            role=artifacts[0].role,
            media_type=artifacts[0].media_type,
            content=b"changed",
        )
        mismatch = client.post(
            "/v1/bundles",
            files=multipart(bundle, (changed, *artifacts[1:])),
            headers={"Idempotency-Key": bundle.idempotency_key},
        )

    assert missing.status_code == 422
    assert mismatch.status_code == 422


def test_ingestion_rejects_large_request() -> None:
    engine = memory_engine()
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", max_request_bytes=10)
    app = create_app(settings, factory)
    bundle, artifacts = matching_bundle()

    with TestClient(app) as client:
        response = client.post(
            "/v1/bundles",
            files=multipart(bundle, artifacts),
            headers={"Idempotency-Key": bundle.idempotency_key},
        )

    assert response.status_code == 413
