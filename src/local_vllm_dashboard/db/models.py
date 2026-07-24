from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class BundleRecord(Base):
    __tablename__ = "bundles"

    bundle_id: Mapped[UUID] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(71), unique=True, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    artifacts: Mapped[list[ArtifactRecord]] = relationship(
        cascade="all, delete-orphan",
        back_populates="bundle",
    )
    observations: Mapped[list[ObservationRecord]] = relationship(
        cascade="all, delete-orphan",
        back_populates="bundle",
    )


class ArtifactRecord(Base):
    __tablename__ = "raw_artifact_provenance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bundle_id: Mapped[UUID] = mapped_column(ForeignKey("bundles.bundle_id"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    digest: Mapped[str] = mapped_column(String(71), nullable=False)
    bundle: Mapped[BundleRecord] = relationship(back_populates="artifacts")


class ObservationRecord(Base):
    __tablename__ = "observations"
    __table_args__ = (UniqueConstraint("bundle_id", "observation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bundle_id: Mapped[UUID] = mapped_column(ForeignKey("bundles.bundle_id"), nullable=False)
    observation_id: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    configuration: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    source: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    bundle: Mapped[BundleRecord] = relationship(back_populates="observations")
    metrics: Mapped[list[MetricRecord]] = relationship(
        cascade="all, delete-orphan",
        back_populates="observation",
    )


class MetricRecord(Base):
    __tablename__ = "metric_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_record_id: Mapped[int] = mapped_column(
        ForeignKey("observations.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregation: Mapped[str] = mapped_column(String(64), nullable=False)
    observation: Mapped[ObservationRecord] = relationship(back_populates="metrics")
