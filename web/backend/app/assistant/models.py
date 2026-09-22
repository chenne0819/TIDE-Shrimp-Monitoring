from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base, utcnow


class Conversation(Base):
    __tablename__ = "assistant_conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(100), default="新的分析")
    demo: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    active_message_id: Mapped[str | None] = mapped_column(String(36))


class Message(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (UniqueConstraint("conversation_id", "request_id", "role"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("assistant_conversations.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    position: Mapped[int] = mapped_column()
    role: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="planning", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    board: Mapped[dict | None] = mapped_column(JSON)
    followups: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(String(400))


class Activity(Base):
    """Observed execution steps, added without altering existing chat tables."""
    __tablename__ = "assistant_activity"
    __table_args__ = (UniqueConstraint("message_id", "kind"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("assistant_messages.id"), index=True)
    position: Mapped[int] = mapped_column()
    kind: Mapped[str] = mapped_column(String(12))
    label: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(12))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[str] = mapped_column(String(600), default="")
    activity_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class AssistantResult(Base):
    """Trusted computed facts and the selected plan, without changing old columns."""
    __tablename__ = "assistant_results"
    message_id: Mapped[str] = mapped_column(ForeignKey("assistant_messages.id"), primary_key=True)
    facts: Mapped[dict] = mapped_column(JSON, default=dict)
    plan: Mapped[dict | None] = mapped_column(JSON)
    presentation: Mapped[str] = mapped_column(String(10), default="answer")
