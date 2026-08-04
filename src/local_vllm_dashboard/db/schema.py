from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from local_vllm_dashboard.db.models import Base, BundleRecord, DependencyRevisionRecord


def dependency_commits(payload: dict[str, object]) -> tuple[tuple[str, str], ...]:
    environment = payload.get("environment")
    if not isinstance(environment, dict):
        return ()
    extensions = environment.get("extensions")
    if not isinstance(extensions, dict):
        return ()
    return tuple(
        (name, revision)
        for name, revision in extensions.items()
        if isinstance(name, str)
        and name.endswith("_commit")
        and isinstance(revision, str)
        and revision
    )


def backfill_dependency_revisions(engine: Engine) -> None:
    with Session(engine) as session:
        existing = set(session.execute(select(DependencyRevisionRecord.bundle_id)).scalars())
        bundles = session.scalars(select(BundleRecord)).all()
        for bundle in bundles:
            if bundle.bundle_id in existing:
                continue
            bundle.dependency_revisions = [
                DependencyRevisionRecord(name=name, revision=revision)
                for name, revision in dependency_commits(bundle.payload)
            ]
        session.commit()


def migrate_artifact_storage(engine: Engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("raw_artifact_provenance")}
    statements = []
    if "media_type" not in columns:
        statements.append("ALTER TABLE raw_artifact_provenance ADD COLUMN media_type VARCHAR(128)")
    if "content" not in columns:
        statements.append("ALTER TABLE raw_artifact_provenance ADD COLUMN content BLOB")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text(
                "UPDATE raw_artifact_provenance SET media_type = CASE "
                "WHEN path LIKE '%.json' THEN 'application/json' "
                "WHEN path LIKE '%.yaml' OR path LIKE '%.yml' THEN 'application/yaml' "
                "ELSE 'application/octet-stream' END WHERE media_type IS NULL"
            )
        )
        connection.execute(
            text("UPDATE raw_artifact_provenance SET content = :empty WHERE content IS NULL"),
            {"empty": b""},
        )


def initialize_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    migrate_artifact_storage(engine)
    backfill_dependency_revisions(engine)
