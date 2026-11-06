"""
SQLAlchemy 2.0 ORM Models for RecallOps Operational Truth.
Conforms strictly to the Database Lead's master schema (docs/database-contract.md):
1. engineers
2. services
3. deploys
4. alerts
5. incidents
6. log_lines
7. fix_attempts
8. agent_suggestions
9. replay_results
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from backend.app.db.base import Base

# Portable JSON type supporting PostgreSQL JSONB and SQLite JSON
JSONType = JSONB().with_variant(JSON(), "sqlite")


class Engineer(Base):
    """Stores Kartly engineering personnel with team ownership and Slack routing."""
    __tablename__ = "engineers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    team: Mapped[str] = mapped_column(String(64), nullable=False)
    slack_handle: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    owned_services: Mapped[List["Service"]] = relationship("Service", back_populates="owner")
    deploys: Mapped[List["Deploy"]] = relationship("Deploy", back_populates="author")
    fix_attempts: Mapped[List["FixAttempt"]] = relationship("FixAttempt", back_populates="engineer")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "team": self.team,
            "slack_handle": self.slack_handle,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Service(Base):
    """Core microservices comprising Kartly's quick-commerce architecture."""
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    team: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("engineers.id", ondelete="SET NULL"), nullable=True
    )
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default="Tier-1", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    owner: Mapped[Optional["Engineer"]] = relationship("Engineer", back_populates="owned_services")
    deploys: Mapped[List["Deploy"]] = relationship("Deploy", back_populates="service", cascade="all, delete-orphan")
    alerts: Mapped[List["Alert"]] = relationship("Alert", back_populates="service", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "team": self.team,
            "owner_id": self.owner_id,
            "tier": self.tier,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Deploy(Base):
    """Deployment registry (queried by get_recent_deploys)."""
    __tablename__ = "deploys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("engineers.id", ondelete="SET NULL"), nullable=True
    )
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    config_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    diff_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    service: Mapped["Service"] = relationship("Service", back_populates="deploys")
    author: Mapped[Optional["Engineer"]] = relationship("Engineer", back_populates="deploys")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "service_id": self.service_id,
            "author_id": self.author_id,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "summary": self.summary,
            "config_change": self.config_change,
            "diff_note": self.diff_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Alert(Base):
    """Operational monitoring threshold breaches triggering incidents."""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    service: Mapped["Service"] = relationship("Service", back_populates="alerts")
    incident: Mapped[Optional["Incident"]] = relationship("Incident", back_populates="alert", uselist=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "service_id": self.service_id,
            "metric": self.metric,
            "threshold": self.threshold,
            "value": self.value,
            "fired_at": self.fired_at.isoformat() if self.fired_at else None,
            "payload": self.payload,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Incident(Base):
    """Master table for operational incidents (INC-0001 to INC-0110)."""
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    alert_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # P1, P2, P3, P4
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="OPEN", index=True
    )  # OPEN, INVESTIGATING, MITIGATED, RESOLVED
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause_family: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    duration_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("severity IN ('P1','P2','P3','P4')", name="chk_incident_severity"),
        CheckConstraint(
            "status IN ('OPEN','INVESTIGATING','MITIGATED','RESOLVED')", name="chk_incident_status"
        ),
    )

    # Relationships
    alert: Mapped[Optional["Alert"]] = relationship("Alert", back_populates="incident")
    log_lines: Mapped[List["LogLine"]] = relationship(
        "LogLine", back_populates="incident", cascade="all, delete-orphan"
    )
    fix_attempts: Mapped[List["FixAttempt"]] = relationship(
        "FixAttempt", back_populates="incident", cascade="all, delete-orphan"
    )
    suggestions: Mapped[List["AgentSuggestion"]] = relationship(
        "AgentSuggestion", back_populates="incident", cascade="all, delete-orphan"
    )
    replay_results: Mapped[List["ReplayResult"]] = relationship(
        "ReplayResult", back_populates="incident", cascade="all, delete-orphan"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "alert_id": self.alert_id,
            "severity": self.severity,
            "status": self.status,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "root_cause": self.root_cause,
            "root_cause_family": self.root_cause_family,
            "duration_min": self.duration_min,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LogLine(Base):
    """Runtime telemetry and log traces (queried by get_logs)."""
    __tablename__ = "log_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="ERROR")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True, default=dict)

    # Relationships
    incident: Mapped["Incident"] = relationship("Incident", back_populates="log_lines")
    service: Mapped["Service"] = relationship("Service")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "service_id": self.service_id,
            "timestamp": self.ts.isoformat() if self.ts else None,
            "level": self.level,
            "message": self.message,
            "metadata": self.metadata_json or {},
        }


class FixAttempt(Base):
    """Remediation attempts and human feedback outcomes."""
    __tablename__ = "fix_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)  # worked, failed, partial
    by_engineer: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("engineers.id", ondelete="SET NULL"), nullable=True
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("outcome IN ('worked','failed','partial')", name="chk_fix_outcome"),
    )

    # Relationships
    incident: Mapped["Incident"] = relationship("Incident", back_populates="fix_attempts")
    engineer: Mapped[Optional["Engineer"]] = relationship("Engineer", back_populates="fix_attempts")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "action": self.action,
            "outcome": self.outcome,
            "by_engineer": self.by_engineer,
            "at": self.at.isoformat() if self.at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AgentSuggestion(Base):
    """Structured triage hypotheses produced by the SRE Agent."""
    __tablename__ = "agent_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    memory_on: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    accepted: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("rank >= 1", name="chk_suggestion_rank"),
    )

    # Relationships
    incident: Mapped["Incident"] = relationship("Incident", back_populates="suggestions")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "hypothesis": self.hypothesis,
            "rank": self.rank,
            "memory_on": self.memory_on,
            "accepted": self.accepted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ReplayResult(Base):
    """Automated benchmark replay evaluation metrics."""
    __tablename__ = "replay_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    incident_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    memory_on: Mapped[bool] = mapped_column(Boolean, nullable=False)
    top1_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    top3_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    minutes_to_hypothesis: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("run_id", "incident_id", "memory_on", name="uq_run_incident_memory"),
    )

    # Relationships
    incident: Mapped["Incident"] = relationship("Incident", back_populates="replay_results")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "incident_id": self.incident_id,
            "memory_on": self.memory_on,
            "top1_correct": self.top1_correct,
            "top3_correct": self.top3_correct,
            "minutes_to_hypothesis": self.minutes_to_hypothesis,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
