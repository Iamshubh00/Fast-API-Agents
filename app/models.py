from datetime import datetime

from sqlalchemy import BigInteger, String, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Alert(Base):
    """A raw security alert that enters the multi-agent pipeline."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)          # edr | siem | ids | manual
    severity_raw: Mapped[str] = mapped_column(String, nullable=False)    # as reported by the source
    raw_event: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String, default="new")           # new|triaging|enriched|correlated|awaiting_approval|closed
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="alert", cascade="all, delete-orphan")


class AgentRun(Base):
    """One agent's output against one alert -- kept as an immutable trace for auditability."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    alert_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("alerts.id", ondelete="CASCADE"))
    agent_name: Mapped[str] = mapped_column(String, nullable=False)      # triage | enrichment | correlation | response
    input_summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict] = mapped_column(JSONB, nullable=False)          # structured JSON result from the model
    model: Mapped[str] = mapped_column(String, nullable=False)
    latency_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    alert: Mapped["Alert"] = relationship(back_populates="agent_runs")


class AuditLog(Base):
    """Append-only. Every mutating action, human or agent, lands here."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor: Mapped[str] = mapped_column(String, nullable=False)           # user sub, or "agent:triage" etc.
    action: Mapped[str] = mapped_column(String, nullable=False)
    target: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
