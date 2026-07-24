from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bundles",
        sa.Column("bundle_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=71), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("bundle_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_table(
        "raw_artifact_provenance",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bundle_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(length=71), nullable=False),
        sa.ForeignKeyConstraint(["bundle_id"], ["bundles.bundle_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bundle_id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.JSON(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["bundle_id"], ["bundles.bundle_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bundle_id", "observation_id"),
    )
    op.create_table(
        "metric_values",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("observation_record_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("aggregation", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["observation_record_id"], ["observations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("metric_values")
    op.drop_table("observations")
    op.drop_table("raw_artifact_provenance")
    op.drop_table("bundles")
