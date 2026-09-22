from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    pond: Mapped[str] = mapped_column(String(80), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    mode: Mapped[str] = mapped_column(String(20), default="general")
    water_policy: Mapped[str] = mapped_column(String(12), default="report")
    max_frames: Mapped[int | None] = mapped_column(Integer)
    source_path: Mapped[str] = mapped_column(String(500))
    source_browser_path: Mapped[str | None] = mapped_column(String(500))
    result_path: Mapped[str | None] = mapped_column(String(500))
    thumbnail_path: Mapped[str | None] = mapped_column(String(500))
    water_label: Mapped[str | None] = mapped_column(String(16))
    water_confidence: Mapped[float | None] = mapped_column(Float)
    shrimp_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_length_mm: Mapped[float | None] = mapped_column(Float)
    avg_width_mm: Mapped[float | None] = mapped_column(Float)
    avg_weight_g: Mapped[float | None] = mapped_column(Float)
    processed_frames: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    artifacts: Mapped[dict] = mapped_column(JSON, default=dict)
    worker_id: Mapped[str | None] = mapped_column(String(100), index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ingest_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    tracks: Mapped[list["Track"]] = relationship(back_populates="job", cascade="all, delete-orphan", lazy="selectin")


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (UniqueConstraint("job_id", "track_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    track_id: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(12), default="Unknown")
    observations: Mapped[int] = mapped_column(Integer, default=0)
    length_mm: Mapped[float | None] = mapped_column(Float)
    width_mm: Mapped[float | None] = mapped_column(Float)
    weight_g: Mapped[float | None] = mapped_column(Float)
    job: Mapped[Job] = relationship(back_populates="tracks")


class Worker(Base):
    __tablename__ = "workers"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="idle")
    current_job_id: Mapped[str | None] = mapped_column(String(36))


def make_engine(url: str):
    options = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, connect_args=options)


def make_session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


def init_database(engine):
    # MVP schema bootstrap. Future schema changes require explicit migrations.
    Base.metadata.create_all(engine)
