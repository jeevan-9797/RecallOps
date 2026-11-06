"""
SQLAlchemy 2.0 ORM Models for RecallOps Operational Truth.
Defines the 9 tables conforming to the Database Lead specification:
1. services
2. engineers
3. deploys
4. alerts
5. incidents
6. log_lines
7. fix_attempts
8. agent_suggestions
9. replay_results
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin


class Service(Base, TimestampMixin):
    """Registered microservice inventory."""
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    owner_team: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), default="tier-1", nullable=False)
    repo_url: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Relationships
    engineers: Mapped[List["Engineer"]] = relationship("Engineer", back_populates="service")
    deploys: Mapped[List["Deploy"]] = relationship("Deploy", back_populates="service")
    incidents: Mapped[List["Incident"]] = relationship("Incident", back_populates="service")


class Engineer(Base, TimestampMixin):
    """Engineers and on-call rotation roster."""
    __tablename__ = "engineers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    slack_handle: Mapped[str] = mapped_column(String(64), nullable=False)
    service_name: Mapped[str] = mapped_column(String(128), ForeignKey("services.name"), nullable=False)
    is_on_call: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    service: Mapped["Service"] = relationship("Service", back_populates="engineers")


class Deploy(Base):
    """Deployment registry (queried by get_recent_deploys)."""
    __tablename__ = "deploys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    service_name: Mapped[str] = mapped_column(String(128), ForeignKey("services.name"), index=True, nullable=False)
    commit_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    author: Mapped[str] = mapped_column(String(128), nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="success", nullable=False)  # success, canary, rollback
    deployed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )

    service: Mapped["Service"] = relationship("Service", back_populates="deploys")


class Alert(Base, TimestampMixin):
    """Ingested operational alerts that trigger incidents."""
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    incident_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("incidents.id"), nullable=True)
    service_name: Mapped[str] = mapped_column(String(128), ForeignKey("services.name"), nullable=False)
    symptom: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="CRITICAL", nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    incident: Mapped[Optional["Incident"]] = relationship("Incident", back_populates="alerts")


class Incident(Base, TimestampMixin):
    """Active and resolved incidents."""
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    service_name: Mapped[str] = mapped_column(String(128), ForeignKey("services.name"), index=True, nullable=False)
    symptom: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True, nullable=False)  # created, triaging, resolved
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fix_applied: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    service: Mapped["Service"] = relationship("Service", back_populates="incidents")
    alerts: Mapped[List["Alert"]] = relationship("Alert", back_populates="incident")
    log_lines: Mapped[List["LogLine"]] = relationship("LogLine", back_populates="incident")
    fix_attempts: Mapped[List["FixAttempt"]] = relationship("FixAttempt", back_populates="incident")
    suggestions: Mapped[List["AgentSuggestion"]] = relationship("AgentSuggestion", back_populates="incident")


class LogLine(Base):
    """Runtime telemetry and log traces (queried by get_logs)."""
    __tablename__ = "log_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(64), ForeignKey("incidents.id"), index=True, nullable=False)
    service_name: Mapped[str] = mapped_column(String(128), ForeignKey("services.name"), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )
    level: Mapped[str] = mapped_column(String(16), default="ERROR", nullable=False)  # INFO, WARN, ERROR, FATAL
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict, nullable=True)

    incident: Mapped["Incident"] = relationship("Incident", back_populates="log_lines")


class FixAttempt(Base):
    """Remediation attempts and human feedback outcomes."""
    __tablename__ = "fix_attempts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(64), ForeignKey("incidents.id"), index=True, nullable=False)
    suggestion_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)  # worked, failed, partial
    failure_mode: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warning_directive: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    incident: Mapped["Incident"] = relationship("Incident", back_populates="fix_attempts")


class AgentSuggestion(Base, TimestampMixin):
    """Structured triage output generated by the SRE Agent."""
    __tablename__ = "agent_suggestions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(64), ForeignKey("incidents.id"), index=True, nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    cited_incident_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    failed_fixes_warning: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    likely_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), default="openai/gpt-oss-120b", nullable=False)

    incident: Mapped["Incident"] = relationship("Incident", back_populates="suggestions")


class ReplayResult(Base, TimestampMixin):
    """Historical benchmark evaluation results comparing Memory OFF vs ON."""
    __tablename__ = "replay_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    benchmark_name: Mapped[str] = mapped_column(String(128), default="40_incident_replay_v1", nullable=False)
    incident_id: Mapped[str] = mapped_column(String(64), nullable=False)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    correct_diagnosis: Mapped[bool] = mapped_column(Boolean, nullable=False)
    duration_min: Mapped[float] = mapped_column(Float, nullable=False)
    avoided_negative_fix: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
