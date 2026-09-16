from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CollectionTask(Base):
    __tablename__ = "collection_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(50))
    query: Mapped[str] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    collected: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[str] = mapped_column(String(20), default="single")
    target_count: Mapped[int] = mapped_column(Integer, default=100000)
    shard_total: Mapped[int] = mapped_column(Integer, default=0)
    shard_completed: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("normalized_name", "normalized_phone", name="uq_company_phone"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), index=True)
    normalized_name: Mapped[str] = mapped_column(String(300), index=True)
    phone: Mapped[str] = mapped_column(String(80), index=True)
    normalized_phone: Mapped[str] = mapped_column(String(40), index=True)
    country: Mapped[str] = mapped_column(String(80), default="", index=True)
    verification_status: Mapped[str] = mapped_column(
        String(30), default="pending", index=True
    )
    is_business_phone: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[str] = mapped_column(String(120), default="", index=True)
    website: Mapped[str] = mapped_column(Text, default="")
    relevance: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sources: Mapped[List["SourceRecord"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint("company_id", "source_url", name="uq_company_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("collection_tasks.id"), nullable=True, index=True
    )
    source_type: Mapped[str] = mapped_column(String(50))
    source_url: Mapped[str] = mapped_column(Text)
    keyword: Mapped[str] = mapped_column(String(200), default="")
    external_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    company: Mapped[Company] = relationship(back_populates="sources")


class FailureRecord(Base):
    __tablename__ = "failure_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("collection_tasks.id"), index=True)
    target: Mapped[str] = mapped_column(Text)
    error_type: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TaskShard(Base):
    __tablename__ = "task_shards"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "source_type", "tile_key", "keyword", "match_type",
            name="uq_task_shard",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("collection_tasks.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(50))
    tile_key: Mapped[str] = mapped_column(String(80))
    keyword: Mapped[str] = mapped_column(String(120))
    match_type: Mapped[str] = mapped_column(String(20), default="category")
    west: Mapped[float] = mapped_column(Float)
    south: Mapped[float] = mapped_column(Float)
    east: Mapped[float] = mapped_column(Float)
    north: Mapped[float] = mapped_column(Float)
    cursor: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    collected: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class QualityReport(Base):
    __tablename__ = "quality_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("collection_tasks.id"), unique=True, index=True
    )
    metrics_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TaskCompany(Base):
    __tablename__ = "task_companies"
    __table_args__ = (
        UniqueConstraint("task_id", "company_id", name="uq_task_company"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("collection_tasks.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
