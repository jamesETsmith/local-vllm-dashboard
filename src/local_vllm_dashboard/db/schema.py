from sqlalchemy import select
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


def initialize_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    backfill_dependency_revisions(engine)
