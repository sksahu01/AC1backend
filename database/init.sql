-- =============================================================================
-- AEROCORE — init.sql
-- v4 FINAL POC Edition
-- Run once in Supabase SQL Editor (or psql).
-- Idempotent: uses IF NOT EXISTS / CREATE OR REPLACE throughout.
-- =============================================================================


-- =============================================================================
-- SECTION 1 — 14 TABLES
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 4.1  users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    role            TEXT NOT NULL,
    -- 'coordinator'|'duty_manager'|'aocc'|'vendor'|'hr'|'manager'|'admin'
    authority_level INTEGER DEFAULT 1,
    -- 1=coordinator  2=dept_on_duty  3=duty_mgr  4=aocc  5=airport_head
    airport_id      TEXT NOT NULL,
    department      TEXT,
    designation     TEXT,
    employee_id     TEXT UNIQUE,
    password_hash   TEXT NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 4.2  sessions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    token       TEXT UNIQUE NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_token
    ON sessions(token)
    WHERE is_active = TRUE;

-- ---------------------------------------------------------------------------
-- 4.3  msg_inbox  — MSG DB (Flow 1)   v4: status enum + retry fields
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS msg_inbox (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Sender (from JWT)
    sender_id       UUID REFERENCES users(id) NOT NULL,
    sender_name     TEXT NOT NULL,
    sender_role     TEXT NOT NULL,
    authority_level INTEGER NOT NULL,
    airport_id      TEXT NOT NULL,

    -- Content
    raw_content     TEXT NOT NULL,
    flight_context  TEXT,
    message_type    TEXT NOT NULL,
    -- ONLY: 'task' | 'info' | 'alert' | 'approval' | 'escalation'

    -- v4: Status-based processing guard
    status          TEXT NOT NULL DEFAULT 'unprocessed',
    -- 'unprocessed' | 'in_progress' | 'processed' | 'failed'
    processing_by   TEXT,           -- crawler instance ID (lock)
    processed_at    TIMESTAMPTZ,
    retry_count     INTEGER DEFAULT 0,
    error_log       TEXT,

    received_at     TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Partial index: only unprocessed + unlocked rows visible to crawler
CREATE INDEX IF NOT EXISTS idx_msg_inbox_unprocessed
    ON msg_inbox(received_at ASC)
    WHERE status = 'unprocessed' AND processing_by IS NULL;

-- ---------------------------------------------------------------------------
-- 4.4  chat_inbox  — Chat DB (Flow 2)   v4: status enum + retry fields
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_inbox (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Sender (from JWT)
    sender_id       UUID REFERENCES users(id) NOT NULL,
    sender_name     TEXT NOT NULL,
    sender_role     TEXT NOT NULL,
    airport_id      TEXT NOT NULL,

    -- Content
    raw_content     TEXT NOT NULL,
    query_type      TEXT,
    -- 'general_query' | 'leave' | 'cab' | 'hotel' | NULL (auto-detect)
    session_id      TEXT,
    conversation_history JSONB DEFAULT '[]',

    -- Response (written by Crawler 3 after agent completes)
    response        TEXT,
    response_source TEXT,
    response_data   JSONB DEFAULT '{}',

    -- v4: Status-based processing guard
    status          TEXT NOT NULL DEFAULT 'unprocessed',
    -- 'unprocessed' | 'in_progress' | 'processed' | 'failed'
    processing_by   TEXT,
    processed_at    TIMESTAMPTZ,
    retry_count     INTEGER DEFAULT 0,
    error_log       TEXT,

    received_at     TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_inbox_unprocessed
    ON chat_inbox(received_at ASC)
    WHERE status = 'unprocessed' AND processing_by IS NULL;

CREATE INDEX IF NOT EXISTS idx_chat_inbox_session
    ON chat_inbox(session_id);

-- ---------------------------------------------------------------------------
-- 4.5  ops_cards  — OPS DB (Summarizer output)   v4: status enum + retry
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops_cards (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        TEXT UNIQUE NOT NULL,
    -- format: 'evt_YYYYMMDD_HHMMSS_<airport_id>'
    airport_id      TEXT NOT NULL,

    -- Normalized fields from Summarizer
    type            TEXT NOT NULL,
    -- 'task' | 'info' | 'alert' | 'approval' | 'escalation'
    title           TEXT NOT NULL,
    summary         TEXT NOT NULL,
    actions_required JSONB DEFAULT '[]',
    entities        JSONB DEFAULT '{}',
    -- { flightNo, origin, destination, gate, stand,
    --   ownerRole, requester, eta, etd, resource }

    -- Priority
    urgency_score   INTEGER,            -- 1–5
    priority_score  FLOAT,
    priority_label  TEXT,               -- 'High' | 'Medium' | 'Low'

    -- Timing
    deadline_utc    TIMESTAMPTZ,

    -- Metadata
    authority_level INTEGER DEFAULT 1,
    impact          INTEGER DEFAULT 1,  -- 1–5
    confidence      FLOAT DEFAULT 0.8,  -- 0–1
    dedup_hash      TEXT,
    policy_flags    JSONB DEFAULT '[]',
    lineage         JSONB DEFAULT '{}',
    source_msg_id   UUID REFERENCES msg_inbox(id),

    -- Routing outcome (filled by Crawler 2)
    routed_to       TEXT,
    routing_status  TEXT DEFAULT 'pending',

    -- v4: Status-based processing guard
    status          TEXT NOT NULL DEFAULT 'unprocessed',
    -- 'unprocessed' | 'in_progress' | 'processed' | 'failed'
    processing_by   TEXT,
    processed_at    TIMESTAMPTZ,
    retry_count     INTEGER DEFAULT 0,
    error_log       TEXT,

    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Crawler 2: unprocessed only, highest priority first
CREATE INDEX IF NOT EXISTS idx_ops_cards_unprocessed
    ON ops_cards(priority_score DESC)
    WHERE status = 'unprocessed' AND processing_by IS NULL;

CREATE INDEX IF NOT EXISTS idx_ops_cards_dedup
    ON ops_cards(dedup_hash);

CREATE INDEX IF NOT EXISTS idx_ops_cards_airport
    ON ops_cards(airport_id, type);

-- ---------------------------------------------------------------------------
-- 4.6  tasks  — Kanban rows (Flow 1 output)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id          TEXT UNIQUE NOT NULL,      -- 'tsk_<8-char-hex>'
    airport_id       TEXT NOT NULL,
    ops_card_id      TEXT REFERENCES ops_cards(event_id),
    flight_no        TEXT,

    title            TEXT NOT NULL,
    description      TEXT,

    -- Kanban state machine
    status           TEXT DEFAULT 'New',
    -- 'New' | 'Ack' | 'InProgress' | 'Blocked' | 'Done'

    priority         FLOAT,
    priority_label   TEXT,

    assignee_id      UUID REFERENCES users(id),
    ack_by_id        UUID REFERENCES users(id),
    ack_at_utc       TIMESTAMPTZ,

    sla_deadline_utc TIMESTAMPTZ,

    -- Visibility gating by authority level
    visible_to_levels INTEGER[] DEFAULT '{1,2,3}',
    escalation_level  INTEGER DEFAULT 0,

    labels           JSONB DEFAULT '[]',
    audit            JSONB DEFAULT '[]',
    -- [{ at, by, action, note }]

    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tasks_airport_status
    ON tasks(airport_id, status);

CREATE INDEX IF NOT EXISTS idx_tasks_flight
    ON tasks(flight_no);

CREATE INDEX IF NOT EXISTS idx_tasks_priority
    ON tasks(priority DESC);

CREATE INDEX IF NOT EXISTS idx_tasks_sla_breach
    ON tasks(sla_deadline_utc)
    WHERE status NOT IN ('Done');

-- ---------------------------------------------------------------------------
-- 4.7  activities  — Gantt rows (Flow 1 output)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_id     TEXT UNIQUE NOT NULL,       -- 'act_<8-char-hex>'
    airport_id      TEXT NOT NULL,
    flight_no       TEXT,
    name            TEXT NOT NULL,
    start_utc       TIMESTAMPTZ NOT NULL,
    end_utc         TIMESTAMPTZ,
    depends_on      JSONB DEFAULT '[]',         -- [activity_id, ...]
    resource_type   TEXT,                       -- 'Gate'|'Stand'|'Staff'|'Equipment'
    resource_id     TEXT,
    state           TEXT DEFAULT 'Planned',
    -- 'Planned' | 'Committed' | 'InProgress' | 'Done'
    source_ops_card_ids JSONB DEFAULT '[]',
    critical_path   BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activities_airport
    ON activities(airport_id, start_utc);

CREATE INDEX IF NOT EXISTS idx_activities_flight
    ON activities(flight_no);

-- ---------------------------------------------------------------------------
-- 4.8  roster  — Crew DB (Flow 2: Roster Agent)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS roster (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id         UUID REFERENCES users(id) NOT NULL,
    designation         TEXT NOT NULL,
    duty_date           DATE NOT NULL,
    shift_start_utc     TIMESTAMPTZ NOT NULL,
    shift_end_utc       TIMESTAMPTZ NOT NULL,
    status              TEXT DEFAULT 'Scheduled',
    -- 'Scheduled' | 'OnDuty' | 'Completed' | 'Leave' | 'Standby'
    flight_no           TEXT,
    airport_id          TEXT NOT NULL,
    rest_hours_before   FLOAT,
    is_backup           BOOLEAN DEFAULT FALSE,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_roster_date_desig
    ON roster(duty_date, designation);

CREATE INDEX IF NOT EXISTS idx_roster_employee
    ON roster(employee_id);

CREATE INDEX IF NOT EXISTS idx_roster_backup
    ON roster(is_backup, duty_date, airport_id)
    WHERE is_backup = TRUE;

-- ---------------------------------------------------------------------------
-- 4.9  leave_requests  (Flow 2: Roster Agent output)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leave_requests (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id         UUID REFERENCES users(id) NOT NULL,
    leave_type          TEXT NOT NULL,
    -- 'casual' | 'sick' | 'emergency' | 'planned'
    start_date          DATE NOT NULL,
    end_date            DATE NOT NULL,
    reason              TEXT,
    status              TEXT DEFAULT 'Pending',
    -- 'Pending' | 'Approved' | 'Rejected'
    backup_assigned_to  UUID REFERENCES users(id),
    approved_by         UUID REFERENCES users(id),
    source_chat_id      UUID REFERENCES chat_inbox(id),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 4.10  vendor_tickets  (Flow 2: CabHotel Agent output)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_tickets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id           TEXT UNIQUE NOT NULL,   -- 'vt_<8-char-hex>'
    ticket_type         TEXT NOT NULL,          -- 'cab' | 'hotel'
    requester_id        UUID REFERENCES users(id),
    vendor_id           UUID REFERENCES users(id),
    details             JSONB DEFAULT '{}',
    status              TEXT DEFAULT 'Open',
    -- 'Open'|'Acknowledged'|'InProgress'|'Resolved'|'Escalated'
    resolution_notes    TEXT,
    sla_deadline_utc    TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,
    review_ticket       BOOLEAN DEFAULT FALSE,
    source_chat_id      UUID REFERENCES chat_inbox(id),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 4.11  hr_documents  — RAG Knowledge Base (Flow 2: Query Agent)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hr_documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    doc_type    TEXT NOT NULL,      -- 'policy' | 'sop' | 'faq' | 'playbook'
    department  TEXT,
    tags        JSONB DEFAULT '[]',
    version     TEXT DEFAULT '1.0',
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- POC: full-text search. Production: upgrade to pgvector embeddings.
CREATE INDEX IF NOT EXISTS idx_hr_docs_fts
    ON hr_documents USING gin(to_tsvector('english', content));

-- ---------------------------------------------------------------------------
-- 4.12  leave_balances  (Flow 2: Query Agent + Roster Agent read)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leave_balances (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id     UUID REFERENCES users(id) UNIQUE NOT NULL,
    financial_year  TEXT NOT NULL,
    casual_total    INTEGER DEFAULT 12,
    casual_used     INTEGER DEFAULT 0,
    sick_total      INTEGER DEFAULT 10,
    sick_used       INTEGER DEFAULT 0,
    planned_total   INTEGER DEFAULT 15,
    planned_used    INTEGER DEFAULT 0,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
-- remaining = total - used (computed in query, not stored)

-- ---------------------------------------------------------------------------
-- 4.13  flights  — Reference / Seed Data (Summarizer enrichment)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flights (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flight_no           TEXT NOT NULL,
    origin              TEXT NOT NULL,
    destination         TEXT NOT NULL,
    scheduled_departure TIMESTAMPTZ,
    scheduled_arrival   TIMESTAMPTZ,
    actual_departure    TIMESTAMPTZ,
    actual_arrival      TIMESTAMPTZ,
    gate_assigned       TEXT,
    stand_assigned      TEXT,
    status              TEXT DEFAULT 'Scheduled',
    airport_id          TEXT NOT NULL,
    aircraft_type       TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_flights_no
    ON flights(flight_no);

CREATE INDEX IF NOT EXISTS idx_flights_airport_dep
    ON flights(airport_id, scheduled_departure);

-- ---------------------------------------------------------------------------
-- 4.14  sla_configs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sla_configs (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ops_type                    TEXT NOT NULL,
    -- 'task' | 'alert' | 'approval' | 'escalation' | 'info'
    priority_label              TEXT NOT NULL,
    -- 'High' | 'Medium' | 'Low'
    sla_minutes                 INTEGER NOT NULL,
    escalation_after_minutes    INTEGER NOT NULL,
    airport_id                  TEXT DEFAULT 'DEFAULT',
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);


-- =============================================================================
-- SECTION 2 — NOTIFY TRIGGERS  (Section 5 of spec)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Trigger 1: msg_inbox INSERT → wake Smart Crawler 1
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION notify_msg_inbox()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'msg_inbox_insert',
        json_build_object(
            'id',           NEW.id,
            'airport_id',   NEW.airport_id,
            'message_type', NEW.message_type,
            'received_at',  NEW.received_at
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_msg_inbox_insert ON msg_inbox;
CREATE TRIGGER trg_msg_inbox_insert
    AFTER INSERT ON msg_inbox
    FOR EACH ROW EXECUTE FUNCTION notify_msg_inbox();


-- ---------------------------------------------------------------------------
-- Trigger 2: ops_cards INSERT → wake Smart Crawler 2
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION notify_ops_cards()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'ops_cards_insert',
        json_build_object(
            'id',             NEW.id,
            'event_id',       NEW.event_id,
            'airport_id',     NEW.airport_id,
            'type',           NEW.type,
            'priority_score', NEW.priority_score
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ops_cards_insert ON ops_cards;
CREATE TRIGGER trg_ops_cards_insert
    AFTER INSERT ON ops_cards
    FOR EACH ROW EXECUTE FUNCTION notify_ops_cards();


-- ---------------------------------------------------------------------------
-- Trigger 3: chat_inbox INSERT → wake Smart Crawler 3
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION notify_chat_inbox()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'chat_inbox_insert',
        json_build_object(
            'id',          NEW.id,
            'airport_id',  NEW.airport_id,
            'query_type',  NEW.query_type,
            'received_at', NEW.received_at
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chat_inbox_insert ON chat_inbox;
CREATE TRIGGER trg_chat_inbox_insert
    AFTER INSERT ON chat_inbox
    FOR EACH ROW EXECUTE FUNCTION notify_chat_inbox();


-- =============================================================================
-- SECTION 3 — ATOMIC LOCK RPCs  (Section 5 of spec)
-- FOR UPDATE SKIP LOCKED ensures two concurrent crawler runs
-- never claim the same row.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- lock_msg_batch  — Smart Crawler 1
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lock_msg_batch(batch_size INT, p_crawler_id TEXT)
RETURNS SETOF msg_inbox AS $$
    UPDATE msg_inbox
    SET processing_by = p_crawler_id,
        status        = 'in_progress'
    WHERE id IN (
        SELECT id FROM msg_inbox
        WHERE  status        = 'unprocessed'
          AND  processing_by IS NULL
        ORDER BY received_at ASC
        LIMIT batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
$$ LANGUAGE SQL;

-- ---------------------------------------------------------------------------
-- lock_ops_batch  — Smart Crawler 2
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lock_ops_batch(batch_size INT, p_crawler_id TEXT)
RETURNS SETOF ops_cards AS $$
    UPDATE ops_cards
    SET processing_by = p_crawler_id,
        status        = 'in_progress'
    WHERE id IN (
        SELECT id FROM ops_cards
        WHERE  status        = 'unprocessed'
          AND  processing_by IS NULL
        ORDER BY priority_score DESC   -- highest priority first
        LIMIT batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
$$ LANGUAGE SQL;

-- ---------------------------------------------------------------------------
-- lock_chat_batch  — Smart Crawler 3
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lock_chat_batch(batch_size INT, p_crawler_id TEXT)
RETURNS SETOF chat_inbox AS $$
    UPDATE chat_inbox
    SET processing_by = p_crawler_id,
        status        = 'in_progress'
    WHERE id IN (
        SELECT id FROM chat_inbox
        WHERE  status        = 'unprocessed'
          AND  processing_by IS NULL
        ORDER BY received_at ASC
        LIMIT batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
$$ LANGUAGE SQL;


-- =============================================================================
-- SECTION 4 — SEED DATA
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 2 seed users
--
-- Passwords (bcrypt, cost=12):
--   ops_controller@aerocore.dev  →  "ops_pass_123"
--   duty_manager@aerocore.dev    →  "duty_pass_123"
--
-- Pre-hashed values below are stable bcrypt hashes generated offline.
-- Replace with your own bcrypt hashes before production.
-- ---------------------------------------------------------------------------
INSERT INTO users (
    id, email, name, role, authority_level,
    airport_id, department, designation, employee_id, password_hash
)
VALUES
(
    'aaaaaaaa-0001-0001-0001-000000000001',
    'ops_controller@aerocore.dev',
    'Arnav Kumar',
    'coordinator',
    1,
    'DEL_T3',
    'Ground Operations',
    'Ops Controller',
    'EMP001',
    -- bcrypt hash of "ops_pass_123"  (cost 12)
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewKyNiLXMOrBQSfG'
),
(
    'bbbbbbbb-0002-0002-0002-000000000002',
    'duty_manager@aerocore.dev',
    'Priya Sharma',
    'duty_manager',
    3,
    'DEL_T3',
    'Operations',
    'Duty Manager',
    'EMP002',
    -- bcrypt hash of "duty_pass_123"  (cost 12)
    '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW'
)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- sla_configs — full default set from spec §4.14
-- ---------------------------------------------------------------------------
INSERT INTO sla_configs (ops_type, priority_label, sla_minutes, escalation_after_minutes, airport_id)
VALUES
    ('task',       'High',    15,  5,  'DEFAULT'),
    ('task',       'Medium',  30, 10,  'DEFAULT'),
    ('task',       'Low',     60, 20,  'DEFAULT'),
    ('alert',      'High',     5,  2,  'DEFAULT'),
    ('alert',      'Medium',  15,  5,  'DEFAULT'),
    ('alert',      'Low',     30, 10,  'DEFAULT'),
    ('approval',   'High',    10,  5,  'DEFAULT'),
    ('approval',   'Medium',  20, 10,  'DEFAULT'),
    ('approval',   'Low',     45, 15,  'DEFAULT'),
    ('escalation', 'High',     5,  2,  'DEFAULT'),
    ('escalation', 'Medium',  10,  5,  'DEFAULT'),
    ('info',       'High',    30, 15,  'DEFAULT'),
    ('info',       'Medium',  60, 30,  'DEFAULT'),
    ('info',       'Low',    120, 60,  'DEFAULT')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2 seed hr_documents (for RAG smoke-test)
-- ---------------------------------------------------------------------------
INSERT INTO hr_documents (title, content, doc_type, department, tags, version)
VALUES
(
    'Leave Policy v2.1',
    'Employees are entitled to 12 casual leaves, 10 sick leaves, and 15 planned leaves per financial year. '
    'Casual leave must be applied at least 24 hours in advance except in genuine emergencies. '
    'Sick leave requires a medical certificate for absences exceeding 3 consecutive days. '
    'Planned leave must be applied 7 days in advance and is subject to operational availability. '
    'Emergency leave may be granted on same-day basis at Duty Manager discretion. '
    'Leave balances reset on April 1st each financial year. Unused casual leave lapses; sick and planned may be carried forward up to 5 days.',
    'policy',
    'HR',
    '["leave","hr","policy","casual","sick","planned","emergency"]',
    '2.1'
),
(
    'Ground Operations SOP — Crew Transport',
    'Crew transport must be arranged a minimum of 90 minutes before scheduled departure. '
    'Pre-approved vendors only: OLA Corporate, Meru Cabs, IndiGo Fleet Services. '
    'Vehicle capacity must not exceed 80% for safety compliance. '
    'Night duty (22:00–06:00) requires a minimum 4-seater vehicle for any crew movement. '
    'All transport bookings must be logged in the Ops system with pickup time, vehicle number, and driver contact. '
    'In the event of a vendor no-show, escalate to Duty Manager within 10 minutes. '
    'Hotel accommodation for crew rest must comply with DGCA fatigue management rules: minimum 8 hours rest guaranteed.',
    'sop',
    'Ground Operations',
    '["cab","transport","crew","hotel","vendor","sop","ground_ops"]',
    '1.3'
)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Leave balances for seed users
-- ---------------------------------------------------------------------------
INSERT INTO leave_balances (employee_id, financial_year, casual_used, sick_used, planned_used)
VALUES
    ('aaaaaaaa-0001-0001-0001-000000000001', '2025-26', 3, 1, 2),
    ('bbbbbbbb-0002-0002-0002-000000000002', '2025-26', 1, 0, 0)
ON CONFLICT (employee_id) DO NOTHING;


-- =============================================================================
-- END OF init.sql
-- =============================================================================
