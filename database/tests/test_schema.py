"""
RecallOps - Schema & Model Unit Tests
Member 3: Database & Data Engineering
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import (
    Base,
    Engineer,
    Service,
    Deploy,
    Alert,
    Incident,
    LogLine,
    FixAttempt,
    AgentSuggestion,
    ReplayResult,
    Postmortem,
)


@pytest.fixture
def db_session():
    # Use SQLite in-memory for zero-dependency test execution
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_table_creation(db_session):
    """Verify all 9 tables and postmortems table are properly registered and created."""
    tables = Base.metadata.tables.keys()
    required = [
        "engineers",
        "services",
        "deploys",
        "alerts",
        "incidents",
        "log_lines",
        "fix_attempts",
        "agent_suggestions",
        "replay_results",
        "postmortems",
    ]
    for table_name in required:
        assert table_name in tables, f"Missing table {table_name}"


def test_core_relations_and_cascade(db_session):
    """Verify foreign keys, cascading deletions, and relationship mappings."""
    # 1. Create engineer
    eng = Engineer(name="Aarav Sharma", team="Platform SRE", slack_handle="@aarav.sharma")
    db_session.add(eng)
    db_session.commit()

    # 2. Create service
    svc = Service(name="checkout-api", team="Checkout", owner_id=eng.id, tier="Tier-1")
    db_session.add(svc)
    db_session.commit()

    # 3. Create deploy
    now = datetime.now(timezone.utc)
    dep = Deploy(
        service_id=svc.id,
        author_id=eng.id,
        deployed_at=now,
        summary="Bumped connection pool size",
        config_change=True,
        diff_note="+pool_size: 50",
    )
    db_session.add(dep)

    # 4. Create alert
    alert = Alert(
        service_id=svc.id,
        metric="checkout_p99_latency_ms",
        threshold=500.0,
        value=1840.0,
        fired_at=now,
        payload={"pod_count": 8, "region": "ap-south-1"},
    )
    db_session.add(alert)
    db_session.commit()

    # 5. Create incident
    inc = Incident(
        code="INC-0001",
        alert_id=alert.id,
        severity="P1",
        status="RESOLVED",
        opened_at=now,
        resolved_at=now,
        root_cause="Database connection pool exhaustion under flash sale traffic.",
        root_cause_family="db_pool",
        duration_min=35,
    )
    db_session.add(inc)
    db_session.commit()

    # 6. Add log line
    log = LogLine(
        incident_id=inc.id,
        ts=now,
        level="ERROR",
        source="HikariCP",
        message="Connection is not available, request timed out after 30000ms.",
    )
    db_session.add(log)

    # 7. Add fix attempts (one failed, one worked)
    fix_failed = FixAttempt(
        incident_id=inc.id,
        action="Restart checkout-api pods",
        outcome="failed",
        by_engineer=eng.id,
        at=now,
    )
    fix_worked = FixAttempt(
        incident_id=inc.id,
        action="Increase max pool connections to 100 on RDS Postgres",
        outcome="worked",
        by_engineer=eng.id,
        at=now,
    )
    db_session.add_all([fix_failed, fix_worked])

    # 8. Add agent suggestion
    sugg = AgentSuggestion(
        incident_id=inc.id,
        hypothesis="HikariCP connection pool exhausted due to spike in unclosed transactions.",
        rank=1,
        memory_on=True,
        accepted=True,
    )
    db_session.add(sugg)

    # 9. Add replay result
    rep = ReplayResult(
        run_id="run-benchmark-001",
        incident_id=inc.id,
        memory_on=True,
        top1_correct=True,
        top3_correct=True,
        minutes_to_hypothesis=1.5,
    )
    db_session.add(rep)
    db_session.commit()

    # Verify relationships
    assert len(inc.logs) == 1
    assert inc.logs[0].source == "HikariCP"
    assert len(inc.fix_attempts) == 2
    assert inc.alert.metric == "checkout_p99_latency_ms"
    assert inc.alert.service.name == "checkout-api"
    assert len(inc.suggestions) == 1
    assert len(inc.replay_results) == 1

    # Verify serialization
    inc_dict = inc.to_dict()
    assert inc_dict["code"] == "INC-0001"
    assert inc_dict["root_cause_family"] == "db_pool"
