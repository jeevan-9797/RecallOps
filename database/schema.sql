-- ==============================================================================
-- RecallOps - Master PostgreSQL Schema
-- Fictional Company: Kartly SRE Operations
-- Member 3: Database & Data Engineering
-- ==============================================================================

-- Drop tables in reverse foreign-key dependency order
DROP TABLE IF EXISTS replay_results CASCADE;
DROP TABLE IF EXISTS agent_suggestions CASCADE;
DROP TABLE IF EXISTS postmortems CASCADE;
DROP TABLE IF EXISTS fix_attempts CASCADE;
DROP TABLE IF EXISTS log_lines CASCADE;
DROP TABLE IF EXISTS incidents CASCADE;
DROP TABLE IF EXISTS alerts CASCADE;
DROP TABLE IF EXISTS deploys CASCADE;
DROP TABLE IF EXISTS services CASCADE;
DROP TABLE IF EXISTS engineers CASCADE;

-- -----------------------------------------------------------------------------
-- TABLE 2: engineers
-- -----------------------------------------------------------------------------
CREATE TABLE engineers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    team VARCHAR(64) NOT NULL,
    slack_handle VARCHAR(64) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- TABLE 1: services
-- -----------------------------------------------------------------------------
CREATE TABLE services (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    team VARCHAR(64) NOT NULL,
    owner_id INTEGER REFERENCES engineers(id) ON DELETE SET NULL,
    tier VARCHAR(16) NOT NULL DEFAULT 'Tier-1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- TABLE 3: deploys
-- -----------------------------------------------------------------------------
CREATE TABLE deploys (
    id SERIAL PRIMARY KEY,
    service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    author_id INTEGER REFERENCES engineers(id) ON DELETE SET NULL,
    deployed_at TIMESTAMPTZ NOT NULL,
    summary TEXT NOT NULL,
    config_change BOOLEAN NOT NULL DEFAULT FALSE,
    diff_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- TABLE 4: alerts
-- -----------------------------------------------------------------------------
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    metric VARCHAR(128) NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    fired_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- TABLE 5: incidents
-- -----------------------------------------------------------------------------
CREATE TABLE incidents (
    id SERIAL PRIMARY KEY,
    code VARCHAR(32) UNIQUE NOT NULL,
    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    severity VARCHAR(16) NOT NULL CHECK (severity IN ('P1', 'P2', 'P3', 'P4')),
    status VARCHAR(32) NOT NULL CHECK (status IN ('OPEN', 'INVESTIGATING', 'MITIGATED', 'RESOLVED')),
    opened_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    root_cause TEXT NOT NULL,
    root_cause_family VARCHAR(64) NOT NULL,
    duration_min INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_incident_resolved_after_opened CHECK (resolved_at IS NULL OR resolved_at >= opened_at)
);

-- -----------------------------------------------------------------------------
-- TABLE 6: log_lines
-- -----------------------------------------------------------------------------
CREATE TABLE log_lines (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    ts TIMESTAMPTZ NOT NULL,
    level VARCHAR(16) NOT NULL CHECK (level IN ('DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL')),
    source VARCHAR(64) NOT NULL,
    message TEXT NOT NULL
);

-- -----------------------------------------------------------------------------
-- TABLE 7: fix_attempts
-- -----------------------------------------------------------------------------
CREATE TABLE fix_attempts (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    outcome VARCHAR(32) NOT NULL CHECK (outcome IN ('worked', 'failed', 'partial')),
    by_engineer INTEGER REFERENCES engineers(id) ON DELETE SET NULL,
    at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- TABLE 8: agent_suggestions
-- -----------------------------------------------------------------------------
CREATE TABLE agent_suggestions (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    hypothesis TEXT NOT NULL,
    rank INTEGER NOT NULL CHECK (rank >= 1),
    memory_on BOOLEAN NOT NULL DEFAULT TRUE,
    accepted BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- TABLE 9: replay_results
-- -----------------------------------------------------------------------------
CREATE TABLE replay_results (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    memory_on BOOLEAN NOT NULL,
    top1_correct BOOLEAN NOT NULL,
    top3_correct BOOLEAN NOT NULL,
    minutes_to_hypothesis DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_run_incident_memory UNIQUE (run_id, incident_id, memory_on)
);

-- -----------------------------------------------------------------------------
-- OPTIONAL PROPOSED TABLE: postmortems (Pending Backend approval)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS postmortems (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER UNIQUE NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    timeline_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    preventative_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    published_at TIMESTAMPTZ,
    author_id INTEGER REFERENCES engineers(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- INDEXES FOR OPERATIONAL PERFORMANCE & AGENT QUERIES
-- -----------------------------------------------------------------------------
CREATE INDEX idx_services_team ON services(team);
CREATE INDEX idx_services_tier ON services(tier);

CREATE INDEX idx_deploys_service_deployed ON deploys(service_id, deployed_at DESC);
CREATE INDEX idx_deploys_deployed_at ON deploys(deployed_at DESC);

CREATE INDEX idx_alerts_service_fired ON alerts(service_id, fired_at DESC);
CREATE INDEX idx_alerts_metric ON alerts(metric);

CREATE INDEX idx_incidents_code ON incidents(code);
CREATE INDEX idx_incidents_status ON incidents(status);
CREATE INDEX idx_incidents_severity ON incidents(severity);
CREATE INDEX idx_incidents_opened_at ON incidents(opened_at DESC);
CREATE INDEX idx_incidents_family ON incidents(root_cause_family);

CREATE INDEX idx_log_lines_incident_ts ON log_lines(incident_id, ts ASC);
CREATE INDEX idx_log_lines_level ON log_lines(level);

CREATE INDEX idx_fix_attempts_incident ON fix_attempts(incident_id);
CREATE INDEX idx_fix_attempts_outcome ON fix_attempts(outcome);

CREATE INDEX idx_agent_suggestions_incident ON agent_suggestions(incident_id);
CREATE INDEX idx_replay_results_run ON replay_results(run_id);
