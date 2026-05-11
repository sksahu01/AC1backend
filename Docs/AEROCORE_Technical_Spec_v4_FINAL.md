# AEROCORE — Agentic AI Operations Platform
## Complete Technical Specification — v4 FINAL (POC Edition)
### Python (FastAPI) + Supabase PostgreSQL + asyncpg
### Dual-Flow Architecture · Smart Crawler · No Orchestration

---

> **POC Scope:**
> No MS Teams. No Email. No Call integration.
> Two ingress UI components only: **Message Box** (operational channel) and **QAgent/QBOT** (chat interface).
> This document is fully self-contained. No cross-references to any prior version.

---

## TABLE OF CONTENTS

1. [v4 Changes Summary](#1-v4-changes-summary)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Frontend Ingress Components](#3-frontend-ingress-components)
4. [Database Schema — All 14 Tables](#4-database-schema--all-14-tables)
5. [PostgreSQL NOTIFY Triggers](#5-postgresql-notify-triggers)
6. [Python LISTEN Setup (asyncpg)](#6-python-listen-setup-asyncpg)
7. [FastAPI Lifespan — Scheduler + Listeners](#7-fastapi-lifespan--scheduler--listeners)
8. [Layer 1 — Login / Auth](#8-layer-1--login--auth)
9. [Flow 1 — OPS Channel Pipeline](#9-flow-1--ops-channel-pipeline)
   - 9.1 Ingress: `POST /ingress/message`
   - 9.2 Smart Crawler 1: MSG DB → Summarizer
   - 9.3 Summarizer Agent (full)
   - 9.4 Smart Crawler 2: OPS DB → Router Agent (inline routing)
   - 9.5 Router Agent (full)
10. [Flow 2 — QAgent / Chat Pipeline](#10-flow-2--qagent--chat-pipeline)
    - 10.1 Ingress: `POST /ingress/chat`
    - 10.2 Smart Crawler 3: Chat DB → Agents (inline routing)
    - 10.3 Query Agent + RAG (full)
    - 10.4 CabHotel Agent + Vendor (full)
    - 10.5 Roster Agent + Crew DB (full)
11. [SLA Crawler — Escalation Engine](#11-sla-crawler--escalation-engine)
12. [Dashboard Routes — Kanban, Gantt & Manager](#12-dashboard-routes--kanban-gantt--manager)
13. [Complete Route Registry](#13-complete-route-registry)
14. [End-to-End Flow Diagrams](#14-end-to-end-flow-diagrams)
15. [Project Structure & Stack](#15-project-structure--stack)

---

## 1. v4 Changes Summary

| Change | What Was in v3 | What Is in v4 |
|--------|---------------|----------------|
| Orchestration | Separate `/orchestration/route-ops` and `/orchestration/route-chat` endpoints | **Removed**. Routing logic merged inline into Smart Crawlers 2 and 3 |
| Crawler trigger | Fixed APScheduler interval — polls constantly regardless of data | **NOTIFY/LISTEN** — PostgreSQL trigger fires on INSERT, asyncpg wakes the crawler immediately. 30s fallback sweep retained |
| Processing guard | `is_processed BOOLEAN DEFAULT FALSE` | **Status enum**: `unprocessed → in_progress → processed / failed` |
| Commit timing | Batch commit after all records processed | **Per-record commit** — each record locked, processed, and committed before moving to the next |
| Failure isolation | One exception could stall remaining records | **Per-record try/catch** — failure marks one record `failed`, next record continues unaffected |
| Retry support | None | `retry_count INT` incremented on each failure |
| Orchestration files | `orchestration/ops_corridor.py`, `orchestration/chat_corridor.py` | **Deleted** — logic lives in `crawlers/routing.py` |

**Core rules (unchanged):**
- One message read only once — enforced by status lock (`in_progress` before processing)
- 2 out of 10 unprocessed → crawler fetches exactly 2, never touches the other 8

---

## 2. High-Level Architecture

```
╔══════════════════════════════════════════════════════════════════════╗
║                        FRONTEND (POC UI)                            ║
║                                                                      ║
║  ┌────────────────────────────┐   ┌──────────────────────────────┐  ║
║  │    MESSAGE BOX             │   │    QAGENT / QBOT             │  ║
║  │  (Operational Channel)     │   │    (Chat Sidebar)            │  ║
║  │  Type: Task/Info/Alert/    │   │  Type: General Query/        │  ║
║  │        Approval/Escalation │   │        Leave/Cab/Hotel       │  ║
║  └──────────────┬─────────────┘   └──────────────┬───────────────┘  ║
╚═════════════════╪════════════════════════════════╪═════════════════╝
                  │                                │
      POST /ingress/message           POST /ingress/chat
                  │                                │
                  ▼                                ▼
   ┌──────────────────────────┐    ┌──────────────────────────────┐
   │   msg_inbox (MSG DB)     │    │   chat_inbox (Chat DB)       │
   │   status='unprocessed'   │    │   status='unprocessed'       │
   └──────────────┬───────────┘    └──────────────┬───────────────┘
                  │ NOTIFY: msg_inbox_insert        │ NOTIFY: chat_inbox_insert
                  ▼                                ▼
   ┌──────────────────────────┐    ┌──────────────────────────────┐
   │   SMART CRAWLER 1        │    │   SMART CRAWLER 3            │
   │   (Flow 1 — MSG)         │    │   (Flow 2 — Chat)            │
   │                          │    │                              │
   │  WHERE status=            │    │  WHERE status=               │
   │    'unprocessed'          │    │    'unprocessed'             │
   │  SET 'in_progress' (lock) │    │  SET 'in_progress' (lock)   │
   │  ─── INLINE ───           │    │  ─── INLINE ROUTING ───     │
   │  summarizer_process()     │    │  auto_classify(query_type)  │
   │  INSERT ops_cards         │    │  → query_agent()            │
   │  SET 'processed'/'failed' │    │  → roster_agent()           │
   └──────────────┬────────────┘    │  → cabhotel_agent()         │
                  │                 │  SET 'processed'/'failed'   │
                  │ NOTIFY:         └──────────────┬──────────────┘
                  │ ops_cards_insert               │
                  ▼                               ▼
   ┌──────────────────────────┐    Agent responses:
   │   ops_cards (OPS DB)     │    ├── QAgent Chat Window
   │   status='unprocessed'   │    ├── Manager's Dashboard
   └──────────────┬───────────┘    └── Vendor Dashboard
                  │ NOTIFY: ops_cards_insert
                  ▼
   ┌──────────────────────────┐
   │   SMART CRAWLER 2        │
   │   (Flow 1 — OPS)         │
   │                          │
   │  WHERE status=            │
   │    'unprocessed'          │
   │  ORDER BY priority DESC   │
   │  SET 'in_progress' (lock) │
   │  ─── INLINE ROUTING ───   │
   │  type → router_agent()    │
   │  INSERT tasks             │
   │  INSERT activities        │
   │  SET 'processed'/'failed' │
   └──────────────┬────────────┘
                  ▼
   ┌──────────────────────────┐
   │  tasks + activities      │
   │  (Kanban + Gantt)        │
   └──────────────┬───────────┘
              SLA Crawler (60s interval)
              monitors deadlines →
              escalation → visibility expansion
```

**Core separation:**

| Concern | Flow 1 (OPS) | Flow 2 (QAgent) |
|---------|-------------|-----------------|
| Entry point | Message Box | QAgent / QBOT chat |
| Stored in | `msg_inbox` (MSG DB) | `chat_inbox` (Chat DB) |
| Goes through Summarizer? | **Yes — always** | **No — never** |
| Creates OpsCard? | **Yes** | **No** |
| Orchestration? | **Removed** — Crawler 2 routes inline | **Removed** — Crawler 3 routes inline |
| Output | Kanban + Gantt dashboards | Direct agent response |

---

## 3. Frontend Ingress Components

### 3.1 Message Box (Flow 1 — Operational Channel)

All submissions go through Summarizer. Result always lands on Kanban / Gantt.

```
┌──────────────────────────────────────────────────────────┐
│  OPERATIONAL MESSAGE BOX                                 │
│                                                          │
│  Message Type:                                           │
│  [ Task ] [ Info ] [ Alert ] [ Approval ] [ Escalation ] │
│           (one selection required)                       │
│                                                          │
│  Flight No. (optional): [ ___________ ]                  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Describe the operational event...                 │  │
│  └────────────────────────────────────────────────────┘  │
│  [ Submit ]                                              │
└──────────────────────────────────────────────────────────┘
```

POST → `/ingress/message` → `msg_inbox` → NOTIFY → Smart Crawler 1

### 3.2 QAgent / QBOT (Flow 2 — Chat Interface)

Never creates OpsCards. Always returns a direct response to the chat window.

```
┌──────────────────────────────────────────────────────────┐
│  QAGENT — Internal Helpdesk                              │
│  ┌────────────────────────────────────────────────────┐  │
│  │  You: How many leaves do I have left?              │  │
│  │  AEROCORE: You have 8 casual leaves remaining...   │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Query Type (optional — auto-detected if not set):       │
│  [ General Query ] [ Leave ] [ Cab ] [ Hotel ]           │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Type your question or request...                  │  │
│  └────────────────────────────────────────────────────┘  │
│  [ Send ]                                                │
└──────────────────────────────────────────────────────────┘
```

POST → `/ingress/chat` → `chat_inbox` → NOTIFY → Smart Crawler 3

**Note on QAgent dual role:** `#QRseAgent can act as either` — the QAgent can act as a direct conversational interface OR as a routing layer that invokes the Roster Agent internally. For `general_query` intent `leave_apply`, the Query Agent internally delegates to Roster Agent transparently.

---

## 4. Database Schema — All 14 Tables

### 4.1 `users`
```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    role            TEXT NOT NULL,
    -- 'coordinator'|'duty_manager'|'aocc'|'vendor'|'hr'|'manager'|'admin'
    authority_level INTEGER DEFAULT 1,
    -- 1=coordinator, 2=dept_on_duty, 3=duty_mgr, 4=aocc, 5=airport_head
    airport_id      TEXT NOT NULL,
    department      TEXT,
    designation     TEXT,
    employee_id     TEXT UNIQUE,
    password_hash   TEXT NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### 4.2 `sessions`
```sql
CREATE TABLE sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    token       TEXT UNIQUE NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_sessions_token ON sessions(token) WHERE is_active = TRUE;
```

### 4.3 `msg_inbox` — MSG DB (Flow 1) — v4 UPDATED
```sql
-- v4 CHANGE: is_processed BOOLEAN replaced with status TEXT enum.
--            retry_count and error_log added.
CREATE TABLE msg_inbox (
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
    processing_by   TEXT,               -- crawler instance ID (lock)
    processed_at    TIMESTAMPTZ,
    retry_count     INTEGER DEFAULT 0,
    error_log       TEXT,

    received_at     TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Partial index: only unprocessed + unlocked rows
CREATE INDEX idx_msg_inbox_unprocessed
    ON msg_inbox(received_at ASC)
    WHERE status = 'unprocessed' AND processing_by IS NULL;
```

### 4.4 `chat_inbox` — Chat DB (Flow 2) — v4 UPDATED
```sql
-- v4 CHANGE: is_processed BOOLEAN replaced with status TEXT enum.
CREATE TABLE chat_inbox (
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

CREATE INDEX idx_chat_inbox_unprocessed
    ON chat_inbox(received_at ASC)
    WHERE status = 'unprocessed' AND processing_by IS NULL;
CREATE INDEX idx_chat_inbox_session ON chat_inbox(session_id);
```

### 4.5 `ops_cards` — OPS DB (Flow 1, Summarizer output) — v4 UPDATED
```sql
-- v4 CHANGE: is_processed BOOLEAN replaced with status TEXT enum.
CREATE TABLE ops_cards (
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
CREATE INDEX idx_ops_cards_unprocessed
    ON ops_cards(priority_score DESC)
    WHERE status = 'unprocessed' AND processing_by IS NULL;
CREATE INDEX idx_ops_cards_dedup   ON ops_cards(dedup_hash);
CREATE INDEX idx_ops_cards_airport ON ops_cards(airport_id, type);
```

### 4.6 `tasks` — Kanban rows (Flow 1 output)
```sql
CREATE TABLE tasks (
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

CREATE INDEX idx_tasks_airport_status ON tasks(airport_id, status);
CREATE INDEX idx_tasks_flight         ON tasks(flight_no);
CREATE INDEX idx_tasks_priority       ON tasks(priority DESC);
CREATE INDEX idx_tasks_sla_breach     ON tasks(sla_deadline_utc)
    WHERE status NOT IN ('Done');
```

### 4.7 `activities` — Gantt rows (Flow 1 output)
```sql
CREATE TABLE activities (
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
CREATE INDEX idx_activities_airport ON activities(airport_id, start_utc);
CREATE INDEX idx_activities_flight  ON activities(flight_no);
```

### 4.8 `roster` — Crew DB (Flow 2: Roster Agent)
```sql
CREATE TABLE roster (
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
CREATE INDEX idx_roster_date_desig ON roster(duty_date, designation);
CREATE INDEX idx_roster_employee   ON roster(employee_id);
CREATE INDEX idx_roster_backup     ON roster(is_backup, duty_date, airport_id)
    WHERE is_backup = TRUE;
```

### 4.9 `leave_requests` (Flow 2: Roster Agent output)
```sql
CREATE TABLE leave_requests (
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
```

### 4.10 `vendor_tickets` (Flow 2: CabHotel Agent output)
```sql
CREATE TABLE vendor_tickets (
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
```

### 4.11 `hr_documents` — RAG Knowledge Base (Flow 2: Query Agent)
```sql
CREATE TABLE hr_documents (
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
CREATE INDEX idx_hr_docs_fts
    ON hr_documents USING gin(to_tsvector('english', content));
```

### 4.12 `leave_balances` (Flow 2: Query Agent + Roster Agent read)
```sql
CREATE TABLE leave_balances (
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
```

### 4.13 `flights` — Reference / Seed Data (Summarizer enrichment)
```sql
CREATE TABLE flights (
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
CREATE INDEX idx_flights_no          ON flights(flight_no);
CREATE INDEX idx_flights_airport_dep ON flights(airport_id, scheduled_departure);
```

### 4.14 `sla_configs`
```sql
CREATE TABLE sla_configs (
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
-- Seed data:
-- ('task',       'High',    15,  5,  'DEFAULT')
-- ('task',       'Medium',  30, 10,  'DEFAULT')
-- ('task',       'Low',     60, 20,  'DEFAULT')
-- ('alert',      'High',     5,  2,  'DEFAULT')
-- ('approval',   'High',    10,  5,  'DEFAULT')
-- ('escalation', 'High',     5,  2,  'DEFAULT')
```

---

## 5. PostgreSQL NOTIFY Triggers

These run inside Supabase. On every INSERT to a crawled table, a `pg_notify` fires on a named channel. The Python `asyncpg` connection listening on that channel wakes the appropriate crawler within milliseconds.

```sql
-- ─────────────────────────────────────────────────────────
-- Trigger 1: msg_inbox INSERT → wake Smart Crawler 1
-- ─────────────────────────────────────────────────────────
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

CREATE TRIGGER trg_msg_inbox_insert
    AFTER INSERT ON msg_inbox
    FOR EACH ROW EXECUTE FUNCTION notify_msg_inbox();


-- ─────────────────────────────────────────────────────────
-- Trigger 2: ops_cards INSERT → wake Smart Crawler 2
-- ─────────────────────────────────────────────────────────
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

CREATE TRIGGER trg_ops_cards_insert
    AFTER INSERT ON ops_cards
    FOR EACH ROW EXECUTE FUNCTION notify_ops_cards();


-- ─────────────────────────────────────────────────────────
-- Trigger 3: chat_inbox INSERT → wake Smart Crawler 3
-- ─────────────────────────────────────────────────────────
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

CREATE TRIGGER trg_chat_inbox_insert
    AFTER INSERT ON chat_inbox
    FOR EACH ROW EXECUTE FUNCTION notify_chat_inbox();


-- ─────────────────────────────────────────────────────────
-- Atomic lock RPCs (used by all three crawlers)
-- FOR UPDATE SKIP LOCKED ensures two concurrent crawler runs
-- never claim the same row
-- ─────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION lock_msg_batch(batch_size INT, p_crawler_id TEXT)
RETURNS SETOF msg_inbox AS $$
    UPDATE msg_inbox
    SET processing_by = p_crawler_id,
        status        = 'in_progress'
    WHERE id IN (
        SELECT id FROM msg_inbox
        WHERE status       = 'unprocessed'
          AND processing_by IS NULL
        ORDER BY received_at ASC
        LIMIT batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
$$ LANGUAGE SQL;

CREATE OR REPLACE FUNCTION lock_ops_batch(batch_size INT, p_crawler_id TEXT)
RETURNS SETOF ops_cards AS $$
    UPDATE ops_cards
    SET processing_by = p_crawler_id,
        status        = 'in_progress'
    WHERE id IN (
        SELECT id FROM ops_cards
        WHERE status       = 'unprocessed'
          AND processing_by IS NULL
        ORDER BY priority_score DESC      -- highest priority first
        LIMIT batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
$$ LANGUAGE SQL;

CREATE OR REPLACE FUNCTION lock_chat_batch(batch_size INT, p_crawler_id TEXT)
RETURNS SETOF chat_inbox AS $$
    UPDATE chat_inbox
    SET processing_by = p_crawler_id,
        status        = 'in_progress'
    WHERE id IN (
        SELECT id FROM chat_inbox
        WHERE status       = 'unprocessed'
          AND processing_by IS NULL
        ORDER BY received_at ASC
        LIMIT batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
$$ LANGUAGE SQL;
```

---

## 6. Python LISTEN Setup (asyncpg)

`asyncpg` connects directly to Supabase's PostgreSQL via the direct DB connection string (not the Supabase HTTP client). Each crawler gets its own dedicated connection.

```python
# crawlers/listener.py
import asyncpg
import asyncio
import logging

logger = logging.getLogger("aerocore.listener")

async def start_listeners(smart_crawler_1, smart_crawler_2, smart_crawler_3):
    """
    Opens one asyncpg connection per LISTEN channel.
    Called once during FastAPI lifespan startup.
    Returns connections so they can be closed on shutdown.
    """
    conn_msg  = await asyncpg.connect(settings.SUPABASE_DB_URL)
    conn_ops  = await asyncpg.connect(settings.SUPABASE_DB_URL)
    conn_chat = await asyncpg.connect(settings.SUPABASE_DB_URL)

    # ── Listener 1: msg_inbox → Smart Crawler 1 ─────────────
    async def on_msg_insert(conn, pid, channel, payload):
        logger.info(f"[L1] msg_inbox NOTIFY received")
        await asyncio.sleep(0.3)       # brief debounce to batch rapid inserts
        await smart_crawler_1()

    await conn_msg.add_listener('msg_inbox_insert', on_msg_insert)

    # ── Listener 2: ops_cards → Smart Crawler 2 ─────────────
    async def on_ops_insert(conn, pid, channel, payload):
        logger.info(f"[L2] ops_cards NOTIFY received")
        await asyncio.sleep(0.3)
        await smart_crawler_2()

    await conn_ops.add_listener('ops_cards_insert', on_ops_insert)

    # ── Listener 3: chat_inbox → Smart Crawler 3 ─────────────
    async def on_chat_insert(conn, pid, channel, payload):
        logger.info(f"[L3] chat_inbox NOTIFY received")
        await asyncio.sleep(0.3)
        await smart_crawler_3()

    await conn_chat.add_listener('chat_inbox_insert', on_chat_insert)

    logger.info("All LISTEN channels active.")
    return conn_msg, conn_ops, conn_chat
```

---

## 7. FastAPI Lifespan — Scheduler + Listeners

```python
# main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from crawlers.listener     import start_listeners
from crawlers.msg_crawler  import smart_crawler_1
from crawlers.ops_crawler  import smart_crawler_2
from crawlers.chat_crawler import smart_crawler_3
from crawlers.sla_crawler  import crawl_sla_breaches

scheduler        = AsyncIOScheduler(timezone="UTC")
_listener_conns  = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Start NOTIFY listeners (primary trigger) ─────────────
    conns = await start_listeners(smart_crawler_1, smart_crawler_2, smart_crawler_3)
    _listener_conns.extend(conns)

    # ── Fallback sweeps (resilience — catches any missed NOTIFYs)
    # These only do work if unprocessed rows actually exist.
    scheduler.add_job(smart_crawler_1,    'interval', seconds=30,
                      id='sc1_fallback', max_instances=1, coalesce=True)
    scheduler.add_job(smart_crawler_2,    'interval', seconds=30,
                      id='sc2_fallback', max_instances=1, coalesce=True)
    scheduler.add_job(smart_crawler_3,    'interval', seconds=30,
                      id='sc3_fallback', max_instances=1, coalesce=True)

    # ── SLA Crawler (time-driven, not insert-driven) ──────────
    scheduler.add_job(crawl_sla_breaches, 'interval', seconds=60,
                      id='sla_crawler',  max_instances=1, coalesce=True)

    scheduler.start()
    yield

    scheduler.shutdown()
    for conn in _listener_conns:
        await conn.close()


app = FastAPI(lifespan=lifespan)
```

---

## 8. Layer 1 — Login / Auth

### `POST /auth/login`
**HTTP Method:** POST | **Auth Required:** No

**Input:**
```json
{ "email": "john.doe@airline.com", "password": "plain_password" }
```

**Function:**
```python
async def login(payload: LoginPayload) -> LoginResponse:
    # 1. Fetch user
    result = supabase.table('users') \
        .select('*') \
        .eq('email', payload.email) \
        .eq('is_active', True) \
        .single().execute()

    if not result.data:
        raise HTTPException(401, "Invalid credentials")

    # 2. Verify password
    if not bcrypt.checkpw(payload.password.encode(),
                          result.data['password_hash'].encode()):
        raise HTTPException(401, "Invalid credentials")

    # 3. Generate JWT
    user = result.data
    exp  = datetime.utcnow() + timedelta(hours=12)
    token = jwt.encode({
        "user_id":        user['id'],
        "role":           user['role'],
        "authority_level":user['authority_level'],
        "airport_id":     user['airport_id'],
        "exp":            exp
    }, settings.SECRET_KEY, algorithm="HS256")

    # 4. Store session
    supabase.table('sessions').insert({
        "user_id":    user['id'],
        "token":      token,
        "expires_at": exp.isoformat(),
        "is_active":  True
    }).execute()

    return { "token": token, "user": user, "expires_at": exp }
```

**Output:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiJ9...",
  "user": {
    "id": "uuid",
    "name": "John Doe",
    "role": "duty_manager",
    "authority_level": 3,
    "airport_id": "DEL_T3"
  },
  "expires_at": "2026-02-26T19:20:00Z"
}
```

### `POST /auth/logout`
**HTTP Method:** POST | **Auth Required:** Yes
```python
async def logout(token: str) -> dict:
    supabase.table('sessions') \
        .update({'is_active': False}) \
        .eq('token', token).execute()
    return {"message": "Logged out"}
```

### `GET /auth/me`
**HTTP Method:** GET | **Auth Required:** Yes
**Output:** Full user object from `users` table.

### Auth Middleware (applied to ALL routes except `/auth/login`)
```python
async def verify_token(request: Request) -> User:
    token   = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
    # Raises 401 if expired or signature invalid

    session = supabase.table('sessions').select('id') \
        .eq('token', token).eq('is_active', True) \
        .gte('expires_at', datetime.utcnow().isoformat()) \
        .single().execute()
    if not session.data:
        raise HTTPException(401, "Session invalid or expired")

    request.state.user = User(**payload)
```

---

## 9. Flow 1 — OPS Channel Pipeline

```
Message Box → msg_inbox → NOTIFY → Smart Crawler 1 → Summarizer (inline)
           → ops_cards → NOTIFY → Smart Crawler 2 → Router Agent (inline)
           → tasks + activities → Kanban + Gantt
```

### 9.1 Ingress: `POST /ingress/message`
**HTTP Method:** POST | **Auth Required:** Yes

**Input:**
```json
{
  "raw_content": "Gate change needed for 6E-245 from gate 22 to 28. Stand conflict. ETD 07:55.",
  "message_type": "task",
  "flight_context": "6E245"
}
```

**Validation:**
```python
ALLOWED_TYPES_FLOW1 = {'task', 'info', 'alert', 'approval', 'escalation'}
# message_type must be in ALLOWED_TYPES_FLOW1
# raw_content must not be blank
# flight_context is optional
```

**Function:**
```python
async def ingest_message(payload: IngestMessagePayload, user: User) -> dict:
    if payload.message_type not in ALLOWED_TYPES_FLOW1:
        raise HTTPException(400, f"message_type must be one of {ALLOWED_TYPES_FLOW1}")
    if not payload.raw_content.strip():
        raise HTTPException(400, "raw_content cannot be empty")

    result = supabase.table('msg_inbox').insert({
        "sender_id":       user.id,
        "sender_name":     user.name,
        "sender_role":     user.role,
        "authority_level": user.authority_level,
        "airport_id":      user.airport_id,
        "raw_content":     payload.raw_content.strip(),
        "flight_context":  payload.flight_context,
        "message_type":    payload.message_type,
        "status":          "unprocessed",    # v4: enum, triggers NOTIFY
        "received_at":     datetime.utcnow().isoformat()
    }).execute()
    # INSERT fires trg_msg_inbox_insert → pg_notify('msg_inbox_insert')
    # → asyncpg listener wakes → smart_crawler_1() called within ~300ms

    return {
        "msg_id":      result.data[0]['id'],
        "status":      "queued",
        "pipeline":    "ops_flow",
        "received_at": result.data[0]['received_at']
    }
```

**Output:**
```json
{
  "msg_id": "3f7a1b2c-...",
  "status": "queued",
  "pipeline": "ops_flow",
  "received_at": "2026-02-26T07:20:01Z"
}
```

---

### 9.2 Smart Crawler 1: MSG DB → Summarizer (inline)

**Wakes on:** NOTIFY `msg_inbox_insert`  
**Fallback sweep:** every 30s  
**Reads:** `msg_inbox WHERE status='unprocessed'`  
**Writes:** `ops_cards` (status='unprocessed'), `msg_inbox.status`

```python
# crawlers/msg_crawler.py
import asyncio
from datetime import datetime
from uuid import uuid4
from db import supabase
from agents.summarizer import summarizer_process
import logging

logger  = logging.getLogger("aerocore.crawler1")
_lock1  = asyncio.Lock()     # prevents concurrent runs from the same instance


async def smart_crawler_1():
    if _lock1.locked():
        logger.debug("[SC1] Already running — skip this trigger")
        return

    async with _lock1:
        crawler_id = f"sc1_{uuid4().hex[:6]}"

        # ── STEP 1: Fetch ONLY unprocessed — already processed rows never appear ──
        # If 8 of 10 records are processed, exactly 2 are returned.
        result = supabase.rpc('lock_msg_batch', {
            'batch_size': settings.MSG_BATCH_SIZE,
            'p_crawler_id': crawler_id
        }).execute()
        records = result.data or []

        if not records:
            logger.debug("[SC1] No unprocessed messages.")
            return

        logger.info(f"[SC1] Processing {len(records)} messages.")

        # ── STEP 2: ONE BY ONE — never batch-commit ───────────────────────────
        for msg in records:
            try:
                # Call Summarizer inline — no HTTP hop, no orchestration
                ops_card = await summarizer_process(msg)

                if ops_card:
                    # INSERT ops_cards fires NOTIFY → wakes Smart Crawler 2
                    supabase.table('ops_cards').insert(ops_card).execute()
                    logger.info(f"[SC1] OpsCard created: {ops_card['event_id']}")
                else:
                    logger.info(f"[SC1] Msg {msg['id']} suppressed (duplicate).")

                # IMMEDIATE per-record commit — don't wait for other records
                supabase.table('msg_inbox').update({
                    "status":        "processed",
                    "processed_at":  datetime.utcnow().isoformat(),
                    "processing_by": None
                }).eq('id', msg['id']).execute()

            except Exception as e:
                logger.error(f"[SC1] Failed on {msg['id']}: {e}")

                # Mark failed — does NOT block remaining records
                supabase.table('msg_inbox').update({
                    "status":        "failed",
                    "error_log":     str(e),
                    "retry_count":   msg.get('retry_count', 0) + 1,
                    "processing_by": None
                }).eq('id', msg['id']).execute()
                continue    # ← move to next record regardless
```

---

### 9.3 Summarizer Agent

Called inline by Smart Crawler 1. No HTTP hop.

#### `POST /agents/summarizer/process` (also testable externally)
**HTTP Method:** POST | **Auth Required:** Yes

**Input:**
```json
{
  "id": "uuid",
  "sender_name": "John Doe",
  "sender_role": "duty_manager",
  "authority_level": 3,
  "airport_id": "DEL_T3",
  "raw_content": "Gate change needed for 6E-245 from gate 22 to 28. Stand conflict. ETD 07:55.",
  "message_type": "task",
  "flight_context": "6E245",
  "received_at": "2026-02-26T07:20:00Z"
}
```

**Function:**
```python
# agents/summarizer.py
async def summarizer_process(msg: dict) -> dict | None:

    # ─────────────────────────────────────────────────────
    # STEP 1: DEDUPLICATION
    # ─────────────────────────────────────────────────────
    today      = datetime.utcnow().date().isoformat()
    hash_input = (f"{msg.get('flight_context','')}:"
                  f"{msg['message_type']}:"
                  f"{msg['airport_id']}:{today}")
    dedup_hash = hashlib.sha256(hash_input.encode()).hexdigest()

    existing = supabase.table('ops_cards') \
        .select('id') \
        .eq('dedup_hash', dedup_hash) \
        .gte('created_at', (datetime.utcnow() - timedelta(hours=2)).isoformat()) \
        .execute().data

    if existing:
        return None     # duplicate suppressed — no OpsCard created

    # ─────────────────────────────────────────────────────
    # STEP 2: FLIGHT ENRICHMENT
    # ─────────────────────────────────────────────────────
    flight_details = {}
    if msg.get('flight_context'):
        today_start = datetime.utcnow().replace(hour=0,  minute=0,  second=0).isoformat()
        today_end   = datetime.utcnow().replace(hour=23, minute=59, second=59).isoformat()
        f_result = supabase.table('flights') \
            .select('*') \
            .eq('flight_no', msg['flight_context']) \
            .gte('scheduled_departure', today_start) \
            .lte('scheduled_departure', today_end) \
            .limit(1).execute()
        if f_result.data:
            f = f_result.data[0]
            flight_details = {
                "origin":       f['origin'],
                "destination":  f['destination'],
                "gate":         f['gate_assigned'],
                "stand":        f['stand_assigned'],
                "etd":          f['scheduled_departure'],
                "flightStatus": f['status'],
                "aircraftType": f['aircraft_type']
            }

    # ─────────────────────────────────────────────────────
    # STEP 3: LLM CALL
    # ─────────────────────────────────────────────────────
    prompt = f"""
    Operational message from {msg['sender_name']} ({msg['sender_role']},
    Authority Level {msg['authority_level']}).
    Type: {msg['message_type']}
    Message: {msg['raw_content']}
    Flight data from DB: {json.dumps(flight_details)}
    Received at: {msg['received_at']}

    Return ONLY a valid JSON object with these exact keys:
    title (str, max 10 words, action-oriented),
    summary (str, 1-2 sentences, what + why),
    actions_required (list of strings),
    entities (dict with: flightNo, gateFrom, gateTo, stand, ownerRole,
              requester, eta, etd — include all found),
    urgency_score (int 1-5),
    impact (int 1-5),
    confidence (float 0-1),
    deadline_utc (ISO string or null),
    policy_flags (list of strings)
    """
    raw_llm = await call_llm(system="Output only valid JSON, no preamble.", user=prompt)
    parsed  = json.loads(raw_llm)

    # ─────────────────────────────────────────────────────
    # STEP 4: PRIORITY SCORING
    # ─────────────────────────────────────────────────────
    time_left = compute_time_left(parsed.get('deadline_utc'), msg['received_at'])
    score     = compute_priority(
        time_left_min   = time_left,
        urgency_score   = parsed['urgency_score'],
        authority_level = msg['authority_level'],
        impact          = parsed['impact'],
        confidence      = parsed['confidence']
    )
    label = 'High' if score >= 85 else 'Medium' if score >= 70 else 'Low'

    # ─────────────────────────────────────────────────────
    # STEP 5: BUILD OPS CARD
    # ─────────────────────────────────────────────────────
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return {
        "event_id":          f"evt_{ts}_{msg['airport_id']}",
        "airport_id":        msg['airport_id'],
        "type":              msg['message_type'],
        "title":             parsed['title'],
        "summary":           parsed['summary'],
        "actions_required":  parsed['actions_required'],
        "entities":          {**parsed['entities'], **flight_details},
        "urgency_score":     parsed['urgency_score'],
        "priority_score":    score,
        "priority_label":    label,
        "deadline_utc":      parsed.get('deadline_utc'),
        "authority_level":   msg['authority_level'],
        "impact":            parsed['impact'],
        "confidence":        parsed['confidence'],
        "dedup_hash":        dedup_hash,
        "policy_flags":      parsed.get('policy_flags', []),
        "lineage": {
            "origMsgId":  msg['id'],
            "senderName": msg['sender_name'],
            "agent":      "Summarizer@v1.0",
            "createdAt":  datetime.utcnow().isoformat()
        },
        "source_msg_id":  msg['id'],
        "routing_status": "pending",
        "status":         "unprocessed"   # triggers NOTIFY → Smart Crawler 2
    }
```

**Priority formula:**
```python
def compute_priority(time_left_min, urgency_score, authority_level,
                     impact, confidence, is_redundant=False) -> float:
    base           = 50
    time_factor    = max(0.0, min(1.0, (120 - time_left_min) / 120)) * 30
    urgency_factor = urgency_score   * 4
    auth_factor    = authority_level * 3
    impact_factor  = impact          * 5
    conf_adj       = (confidence - 0.7) * 20
    redundancy_pen = -40 if is_redundant else 0
    return round(base + time_factor + urgency_factor + auth_factor +
                 impact_factor + conf_adj + redundancy_pen, 2)
```

**Output (row inserted into `ops_cards`):**
```json
{
  "event_id": "evt_20260226_072000_DEL_T3",
  "type": "task",
  "title": "Gate Change Required — 6E245",
  "summary": "Flight 6E245 requires an immediate gate change from Gate 22 to Gate 28 due to a stand conflict, ETD 07:55 UTC.",
  "actions_required": ["Notify Gate Control to reassign Gate 28", "Update FIDS", "Inform Ground Handling"],
  "entities": { "flightNo": "6E245", "origin": "DEL", "destination": "BOM", "gateFrom": "22", "gateTo": "28", "etd": "2026-02-26T07:55:00Z" },
  "urgency_score": 4,
  "priority_score": 88.3,
  "priority_label": "High",
  "deadline_utc": "2026-02-26T07:35:00Z",
  "status": "unprocessed"
}
```

---

### 9.4 Smart Crawler 2: OPS DB → Router Agent (inline routing)

**Wakes on:** NOTIFY `ops_cards_insert`  
**Fallback sweep:** every 30s  
**Reads:** `ops_cards WHERE status='unprocessed' ORDER BY priority_score DESC`

```python
# crawlers/ops_crawler.py
import asyncio
from datetime import datetime
from uuid import uuid4
from db import supabase
from crawlers.routing import route_ops_card_inline
import logging

logger = logging.getLogger("aerocore.crawler2")
_lock2 = asyncio.Lock()


async def smart_crawler_2():
    if _lock2.locked():
        logger.debug("[SC2] Already running — skip.")
        return

    async with _lock2:
        crawler_id = f"sc2_{uuid4().hex[:6]}"

        # ── STEP 1: Fetch unprocessed OpsCards, highest priority first ────
        result = supabase.rpc('lock_ops_batch', {
            'batch_size':   settings.OPS_BATCH_SIZE,
            'p_crawler_id': crawler_id
        }).execute()
        records = result.data or []

        if not records:
            logger.debug("[SC2] No unprocessed OpsCards.")
            return

        logger.info(f"[SC2] Processing {len(records)} OpsCards.")

        # ── STEP 2: ONE BY ONE ──────────────────────────────────────────
        for card in records:
            try:
                # INLINE ROUTING — replaces /orchestration/route-ops entirely
                result = await route_ops_card_inline(card)

                supabase.table('ops_cards').update({
                    "status":         "processed",
                    "routing_status": "completed",
                    "routed_to":      result['routed_to'],
                    "processed_at":   datetime.utcnow().isoformat(),
                    "processing_by":  None
                }).eq('id', card['id']).execute()

                logger.info(f"[SC2] OpsCard {card['event_id']} → {result['routed_to']}")

            except Exception as e:
                logger.error(f"[SC2] Failed on {card['id']}: {e}")
                supabase.table('ops_cards').update({
                    "status":        "failed",
                    "routing_status":"failed",
                    "error_log":     str(e),
                    "retry_count":   card.get('retry_count', 0) + 1,
                    "processing_by": None
                }).eq('id', card['id']).execute()
                continue
```

**Inline routing function (replaces `/orchestration/route-ops`):**
```python
# crawlers/routing.py
from agents.router import router_agent_process
from agents.roster import roster_agent_process

async def route_ops_card_inline(ops_card: dict) -> dict:
    """
    v4: This function fully replaces /orchestration/route-ops.
    All routing logic lives here — no separate service.

    Routing table for Flow 1:
    ┌─────────────────────────────────────────────────────┐
    │ ops_card.type         │ Agent                       │
    ├───────────────────────┼─────────────────────────────┤
    │ 'task'                │ router_agent_process()      │
    │ 'alert'               │ router_agent_process()      │
    │ 'info'                │ router_agent_process()      │
    │ 'approval'            │ router_agent_process()      │
    │ 'escalation'          │ router_agent_process()      │
    └───────────────────────┴─────────────────────────────┘
    Exception: if entities contain roster-specific keys
    (leaveRequest, staffShortage, crewGap) → also invoke
    roster_agent_process() in parallel.
    """
    result    = await router_agent_process(ops_card)
    entities  = ops_card.get('entities', {})
    if any(k in entities for k in ['leaveRequest', 'staffShortage', 'crewGap']):
        await roster_agent_process({
            'event_type': 'ops_escalation',
            'airport_id': ops_card['airport_id'],
            'ops_card':   ops_card
        })
    return { 'routed_to': 'router_agent', **result }
```

---

### 9.5 Router Agent

Called inline by Smart Crawler 2. Creates Kanban tasks and Gantt activities.

#### `POST /agents/router/process` (also testable externally)
**HTTP Method:** POST | **Auth Required:** Yes  
**Input:** Full OpsCard dict

**Function:**
```python
# agents/router.py
async def router_agent_process(ops_card: dict) -> dict:

    # STEP 1: SLA CONFIG LOOKUP
    sla = supabase.table('sla_configs') \
        .select('sla_minutes, escalation_after_minutes') \
        .eq('ops_type',      ops_card['type']) \
        .eq('priority_label',ops_card['priority_label']) \
        .execute().data
    sla_mins = sla[0]['sla_minutes'] if sla else 30
    sla_deadline = (
        ops_card.get('deadline_utc') or
        (datetime.utcnow() + timedelta(minutes=sla_mins)).isoformat()
    )

    # STEP 2: VISIBILITY DETERMINATION
    def determine_visibility(urgency: int, authority: int) -> list:
        if urgency >= 4 or authority >= 3: return [1, 2, 3]
        if urgency == 3 or authority == 2: return [1, 2]
        return [1]

    visible = determine_visibility(
        ops_card['urgency_score'],
        ops_card['authority_level']
    )

    # STEP 3: CREATE KANBAN TASK
    task_id  = f"tsk_{uuid4().hex[:8]}"
    entities = ops_card.get('entities', {})
    labels   = list(filter(None, [entities.get('flightNo'),
                                   ops_card['type'],
                                   ops_card['priority_label']]))
    supabase.table('tasks').insert({
        "task_id":           task_id,
        "airport_id":        ops_card['airport_id'],
        "ops_card_id":       ops_card['event_id'],
        "flight_no":         entities.get('flightNo'),
        "title":             ops_card['title'],
        "description":       ops_card['summary'],
        "status":            "New",
        "priority":          ops_card['priority_score'],
        "priority_label":    ops_card['priority_label'],
        "sla_deadline_utc":  sla_deadline,
        "visible_to_levels": visible,
        "escalation_level":  0,
        "labels":            labels,
        "audit": [{
            "at":     datetime.utcnow().isoformat(),
            "by":     "RouterAgent",
            "action": "created"
        }]
    }).execute()

    # STEP 4: CREATE GANTT ACTIVITY (only if time-bound entities present)
    activity_id = None
    if entities.get('etd') or entities.get('eta'):
        start = entities.get('etd') or datetime.utcnow().isoformat()
        end   = ops_card.get('deadline_utc') or \
                (datetime.fromisoformat(start) + timedelta(minutes=15)).isoformat()
        activity_id = f"act_{uuid4().hex[:8]}"
        supabase.table('activities').insert({
            "activity_id":          activity_id,
            "airport_id":           ops_card['airport_id'],
            "flight_no":            entities.get('flightNo'),
            "name":                 ops_card['title'],
            "start_utc":            start,
            "end_utc":              end,
            "resource_type":        entities.get('resource', 'Gate'),
            "resource_id":          entities.get('gateTo') or entities.get('standTo'),
            "state":                "Planned",
            "source_ops_card_ids":  [ops_card['event_id']],
            "critical_path":        ops_card['priority_label'] == 'High'
        }).execute()

    return { "task_id": task_id, "activity_id": activity_id }
```

**Output:**
```json
{
  "task_id": "tsk_a1b2c3d4",
  "activity_id": "act_e5f6g7h8",
  "status": "New",
  "priority_label": "High",
  "sla_deadline_utc": "2026-02-26T07:35:00Z",
  "visible_to_levels": [1, 2, 3]
}
```

---

## 10. Flow 2 — QAgent / Chat Pipeline

```
QAgent/QBOT → chat_inbox → NOTIFY → Smart Crawler 3
           → inline routing → Query / Roster / CabHotel Agent
           → response written back → chat window / Manager dashboard
```

### 10.1 Ingress: `POST /ingress/chat`
**HTTP Method:** POST | **Auth Required:** Yes

**Input:**
```json
{
  "raw_content": "How many casual leaves do I have remaining?",
  "query_type": "general_query",
  "session_id": "sess_abc123",
  "conversation_history": [
    { "role": "user",      "content": "Hi" },
    { "role": "assistant", "content": "Hello! How can I help?" }
  ]
}
```

**Validation:**
```python
ALLOWED_QUERY_TYPES = {'general_query', 'leave', 'cab', 'hotel', None}
# query_type is optional — Smart Crawler 3 auto-detects if None
# raw_content must not be blank
```

**Function:**
```python
async def ingest_chat(payload: IngestChatPayload, user: User) -> dict:
    if payload.query_type and payload.query_type not in ALLOWED_QUERY_TYPES:
        raise HTTPException(400, "Invalid query_type")
    if not payload.raw_content.strip():
        raise HTTPException(400, "raw_content cannot be empty")

    result = supabase.table('chat_inbox').insert({
        "sender_id":             user.id,
        "sender_name":           user.name,
        "sender_role":           user.role,
        "airport_id":            user.airport_id,
        "raw_content":           payload.raw_content.strip(),
        "query_type":            payload.query_type,
        "session_id":            payload.session_id,
        "conversation_history":  payload.conversation_history or [],
        "status":                "unprocessed",    # triggers NOTIFY
        "received_at":           datetime.utcnow().isoformat()
    }).execute()
    # INSERT fires trg_chat_inbox_insert → pg_notify('chat_inbox_insert')
    # → asyncpg listener wakes → smart_crawler_3() called within ~300ms

    return {
        "chat_id":    result.data[0]['id'],
        "status":     "queued",
        "pipeline":   "qagent_flow",
        "session_id": payload.session_id
    }
```

**Output:**
```json
{
  "chat_id": "7c3e9f1a-...",
  "status": "queued",
  "pipeline": "qagent_flow",
  "session_id": "sess_abc123"
}
```

---

### 10.2 Smart Crawler 3: Chat DB → Agents (inline routing)

**Wakes on:** NOTIFY `chat_inbox_insert`  
**Fallback sweep:** every 30s  
**Reads:** `chat_inbox WHERE status='unprocessed'`

```python
# crawlers/chat_crawler.py
import asyncio
from datetime import datetime
from uuid import uuid4
from db import supabase
from crawlers.routing import route_chat_inline
import logging

logger = logging.getLogger("aerocore.crawler3")
_lock3 = asyncio.Lock()


async def smart_crawler_3():
    if _lock3.locked():
        logger.debug("[SC3] Already running — skip.")
        return

    async with _lock3:
        crawler_id = f"sc3_{uuid4().hex[:6]}"

        result = supabase.rpc('lock_chat_batch', {
            'batch_size':   settings.CHAT_BATCH_SIZE,
            'p_crawler_id': crawler_id
        }).execute()
        records = result.data or []

        if not records:
            logger.debug("[SC3] No unprocessed chat messages.")
            return

        logger.info(f"[SC3] Processing {len(records)} chat messages.")

        for msg in records:
            try:
                # INLINE ROUTING — replaces /orchestration/route-chat entirely
                result = await route_chat_inline(msg)

                # Write response back to the chat_inbox row
                supabase.table('chat_inbox').update({
                    "status":          "processed",
                    "processed_at":    datetime.utcnow().isoformat(),
                    "processing_by":   None,
                    "response":        result.get('response', ''),
                    "response_source": result.get('agent_used', ''),
                    "response_data":   result.get('data', {})
                }).eq('id', msg['id']).execute()

                logger.info(f"[SC3] Chat {msg['id']} → {result.get('agent_used')}")

            except Exception as e:
                logger.error(f"[SC3] Failed on {msg['id']}: {e}")
                supabase.table('chat_inbox').update({
                    "status":        "failed",
                    "error_log":     str(e),
                    "retry_count":   msg.get('retry_count', 0) + 1,
                    "processing_by": None
                }).eq('id', msg['id']).execute()
                continue
```

**Inline routing function (replaces `/orchestration/route-chat`):**
```python
# crawlers/routing.py (continued)
from agents.query    import query_agent_process
from agents.roster   import roster_agent_process
from agents.cabhotel import cabhotel_agent_process

async def route_chat_inline(chat_msg: dict) -> dict:
    """
    v4: Replaces /orchestration/route-chat entirely.

    Routing table:
    ┌─────────────────┬──────────────────────────────────┐
    │ query_type      │ Agent                            │
    ├─────────────────┼──────────────────────────────────┤
    │ 'general_query' │ query_agent_process()            │
    │ None (auto)     │ auto_classify() → route          │
    │ 'leave'         │ roster_agent_process()           │
    │ 'cab'           │ cabhotel_agent_process()         │
    │ 'hotel'         │ cabhotel_agent_process()         │
    └─────────────────┴──────────────────────────────────┘
    """
    query_type = chat_msg.get('query_type') or auto_classify(chat_msg['raw_content'])

    agent_payload = {
        "chat_id":              chat_msg['id'],
        "query_text":           chat_msg['raw_content'],
        "employee_id":          chat_msg['sender_id'],
        "query_type":           query_type,
        "conversation_history": chat_msg.get('conversation_history', []),
        "context": {
            "sender_role": chat_msg['sender_role'],
            "airport_id":  chat_msg['airport_id']
        }
    }

    AGENT_MAP = {
        'general_query': query_agent_process,
        'leave':         lambda p: roster_agent_process({**p, 'event_type': 'leave_request'}),
        'cab':           lambda p: cabhotel_agent_process({**p, 'ticket_type': 'cab', 'requester_id': p['employee_id']}),
        'hotel':         lambda p: cabhotel_agent_process({**p, 'ticket_type': 'hotel', 'requester_id': p['employee_id']}),
    }

    handler = AGENT_MAP.get(query_type, query_agent_process)
    result  = await handler(agent_payload)
    result['agent_used'] = query_type
    return result


def auto_classify(text: str) -> str:
    """
    Lightweight keyword classifier for when query_type is not set.
    Upgradeable to LLM-based classification.
    """
    t = text.lower()
    if any(w in t for w in ['leave', 'leaves', 'casual', 'sick leave', 'apply leave', 'leave balance']):
        return 'leave'
    if any(w in t for w in ['cab', 'taxi', 'pickup', 'drop', 'vehicle', 'transport']):
        return 'cab'
    if any(w in t for w in ['hotel', 'accommodation', 'room', 'stay', 'check-in']):
        return 'hotel'
    return 'general_query'
```

---

### 10.3 Query Agent + RAG

Called inline by Smart Crawler 3 for `general_query`.

#### `POST /agents/query/process` (also testable externally)
**HTTP Method:** POST | **Auth Required:** Yes

**Input:**
```json
{
  "chat_id": "uuid",
  "query_text": "How many casual leaves do I have remaining?",
  "employee_id": "user_uuid",
  "query_type": "general_query",
  "conversation_history": [...],
  "context": { "sender_role": "coordinator", "airport_id": "DEL_T3" }
}
```

**Function:**
```python
# agents/query.py
async def query_agent_process(payload: dict) -> dict:

    intent = detect_query_intent(payload['query_text'])

    # ── leave_balance ────────────────────────────────────────
    if intent == 'leave_balance':
        lb = supabase.table('leave_balances') \
            .select('*').eq('employee_id', payload['employee_id']) \
            .single().execute().data
        if not lb:
            return {"response": "Leave balance not found.", "source": "hr_database"}
        return {
            "response": (
                f"You have {lb['casual_total']-lb['casual_used']} casual, "
                f"{lb['sick_total']-lb['sick_used']} sick, and "
                f"{lb['planned_total']-lb['planned_used']} planned leaves "
                f"remaining for FY {lb['financial_year']}."
            ),
            "data":   lb,
            "source": "hr_database"
        }

    # ── leave_apply (delegates to Roster Agent) ──────────────
    if intent == 'leave_apply':
        params = await llm_extract_leave_params(payload['query_text'])
        # Returns: { start_date, end_date, leave_type, reason }
        return await roster_agent_process({
            "event_type":  "leave_request",
            "employee_id": payload['employee_id'],
            "chat_id":     payload.get('chat_id'),
            **params
        })

    # ── policy_lookup (RAG over hr_documents) ────────────────
    if intent == 'policy_lookup':
        docs = supabase.table('hr_documents') \
            .select('title, content, doc_type') \
            .eq('is_active', True) \
            .text_search('content', payload['query_text']) \
            .limit(3).execute().data
        context_text = "\n---\n".join([d['content'][:500] for d in docs])
        answer = await call_llm(
            system="Answer based only on the provided documents.",
            user=f"Question: {payload['query_text']}\n\nDocuments:\n{context_text}"
        )
        return {
            "response": answer,
            "sources":  [d['title'] for d in docs],
            "source":   "rag_model"
        }

    # ── roster_query (delegates to Roster Agent) ─────────────
    if intent == 'roster_query':
        return await roster_agent_process({
            "event_type": "query",
            "query_text": payload['query_text'],
            "airport_id": payload['context']['airport_id'],
            "chat_id":    payload.get('chat_id')
        })

    # ── general fallback (RAG + LLM) ─────────────────────────
    docs   = supabase.table('hr_documents').select('content') \
        .text_search('content', payload['query_text']).limit(2).execute().data
    ctx    = "\n".join([d['content'][:400] for d in docs]) if docs else ""
    answer = await call_llm(
        system=QUERY_AGENT_SYSTEM_PROMPT,
        user=build_chat_prompt(payload['query_text'],
                               payload.get('conversation_history', []), ctx)
    )
    return {"response": answer, "source": "llm_rag"}


def detect_query_intent(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ['how many leave', 'leave balance', 'leaves left',
                             'leaves remaining', 'leaves do i have']):
        return 'leave_balance'
    if any(w in t for w in ['apply leave', 'take leave', 'request leave',
                             'want leave', 'need leave from']):
        return 'leave_apply'
    if any(w in t for w in ['policy', 'procedure', 'how do i', 'how to',
                             'sop', 'rule', 'guideline']):
        return 'policy_lookup'
    if any(w in t for w in ['roster', 'who is on duty', 'who is working',
                             'standby', 'duty today', 'shift']):
        return 'roster_query'
    return 'general'
```

**Output:**
```json
{
  "response": "You have 8 casual leaves remaining for FY 2025-26. Total: 12, Used: 4.",
  "intent_detected": "leave_balance",
  "source": "hr_database",
  "action_taken": false,
  "data": { "casual_total": 12, "casual_used": 4, "sick_total": 10, "sick_used": 1 }
}
```

#### `POST /agents/query/chat` — Synchronous chatbot (bypasses crawler)
**HTTP Method:** POST | **Auth Required:** Yes  
**Description:** For immediate QAgent window responses. Calls `query_agent_process()` directly and saves to `chat_inbox` as `processed` (no crawler involved).

**Input:**
```json
{
  "user_message": "What is the sick leave policy?",
  "conversation_history": [...],
  "session_id": "sess_abc123"
}
```

**Function:**
```python
async def query_chat_sync(payload: ChatPayload, user: User) -> dict:
    agent_result = await query_agent_process({
        "chat_id":              None,
        "query_text":           payload.user_message,
        "employee_id":          user.id,
        "query_type":           "general_query",
        "conversation_history": payload.conversation_history or [],
        "context": {"sender_role": user.role, "airport_id": user.airport_id}
    })
    # Log to chat_inbox for session history — already processed
    supabase.table('chat_inbox').insert({
        "sender_id":      user.id, "sender_name": user.name,
        "sender_role":    user.role, "airport_id": user.airport_id,
        "raw_content":    payload.user_message,
        "session_id":     payload.session_id,
        "conversation_history": payload.conversation_history,
        "status":         "processed",          # skip crawler
        "response":       agent_result.get('response'),
        "response_source":agent_result.get('source'),
        "processed_at":   datetime.utcnow().isoformat()
    }).execute()
    return {
        "response":   agent_result['response'],
        "session_id": payload.session_id,
        "sources":    agent_result.get('sources', [])
    }
```

---

### 10.4 CabHotel Agent + Vendor

Called inline by Smart Crawler 3 for `cab` or `hotel` query types.

#### `POST /agents/cabhotel/process` (also testable externally)
**HTTP Method:** POST | **Auth Required:** Yes

**Input:**
```json
{
  "chat_id": "uuid",
  "ticket_type": "cab",
  "requester_id": "user_uuid",
  "airport_id": "DEL_T3",
  "query_text": "Need cab at Terminal 3 tomorrow 04:00, 2 crew members"
}
```

**Function:**
```python
# agents/cabhotel.py
async def cabhotel_agent_process(payload: dict) -> dict:

    ticket_type = payload['ticket_type']

    # STEP 1: EXTRACT DETAILS FROM FREE TEXT (LLM)
    details_raw = await call_llm(
        system=f"Extract a JSON object from this {ticket_type} request. Return only valid JSON.",
        user=payload['query_text']
    )
    details = json.loads(details_raw)
    # cab:   { pickup_location, pickup_time, passengers, notes }
    # hotel: { hotel_name, check_in, check_out, rooms }

    # STEP 2: FIND ASSIGNED VENDOR
    vendor = supabase.table('users') \
        .select('id, name') \
        .eq('role',      'vendor') \
        .eq('airport_id', payload['airport_id']) \
        .eq('is_active',  True) \
        .limit(1).execute().data
    vendor_id   = vendor[0]['id']   if vendor else None
    vendor_name = vendor[0]['name'] if vendor else "Unassigned"

    # STEP 3: CREATE VENDOR TICKET
    ticket_id    = f"vt_{uuid4().hex[:8]}"
    sla_deadline = (datetime.utcnow() + timedelta(minutes=30)).isoformat()
    supabase.table('vendor_tickets').insert({
        "ticket_id":        ticket_id,
        "ticket_type":      ticket_type,
        "requester_id":     payload['requester_id'],
        "vendor_id":        vendor_id,
        "details":          details,
        "status":           "Open",
        "sla_deadline_utc": sla_deadline,
        "source_chat_id":   payload.get('chat_id')
    }).execute()

    return {
        "response": (
            f"Your {ticket_type} request (Ticket: {ticket_id}) has been sent to "
            f"{vendor_name}. Expected response within 30 minutes."
        ),
        "ticket_id":   ticket_id,
        "vendor_name": vendor_name,
        "sla_deadline":sla_deadline,
        "data":        details,
        "source":      "cabhotel_agent"
    }
```

**Output:**
```json
{
  "response": "Your cab request (Ticket: vt_a1b2c3d4) has been sent to Vendor ABC. Expected response within 30 minutes.",
  "ticket_id": "vt_a1b2c3d4",
  "vendor_name": "Taxi Vendor ABC",
  "data": { "pickup_location": "Terminal 3", "pickup_time": "2026-02-27T04:00:00Z", "passengers": 2 }
}
```

#### `PATCH /agents/cabhotel/ticket/{ticket_id}/resolve`
**HTTP Method:** PATCH | **Auth Required:** Yes (vendor role only)  
**Input:** `{ "resolution_notes": "Cab arranged, vehicle MH-01-AB-1234, ETA 03:45" }`
```python
async def resolve_ticket(ticket_id: str, payload, user: User) -> dict:
    # Verify user.role == 'vendor' AND ticket.vendor_id == user.id
    supabase.table('vendor_tickets').update({
        "status":           "Resolved",
        "resolution_notes": payload.resolution_notes,
        "resolved_at":      datetime.utcnow().isoformat()
    }).eq('ticket_id', ticket_id).execute()
    return {"message": "Ticket resolved", "ticket_id": ticket_id}
```

#### `GET /agents/cabhotel/tickets`
**HTTP Method:** GET | **Auth Required:** Yes  
**Query Params:** `status` (opt), `ticket_type` (opt), `airport_id`  
**Output:** Paginated list of vendor tickets visible to this user's role

---

### 10.5 Roster Agent + Crew DB

Called inline by Smart Crawler 3 for `leave` query type, or by Query Agent for `leave_apply` / `roster_query` intents. Outputs appear on Manager's Dashboard.

#### `POST /agents/roster/process` (also testable externally)
**HTTP Method:** POST | **Auth Required:** Yes

**Input:**
```json
{
  "event_type": "leave_request",
  "employee_id": "user_uuid",
  "leave_type": "emergency",
  "start_date": "2026-02-27",
  "end_date": "2026-02-28",
  "reason": "Family emergency",
  "chat_id": "uuid"
}
```

**Function:**
```python
# agents/roster.py
async def roster_agent_process(payload: dict) -> dict:

    event_type = payload.get('event_type', 'leave_request')

    # ── EVENT: leave_request ─────────────────────────────────
    if event_type == 'leave_request':
        emp_id     = payload['employee_id']
        start_date = payload['start_date']
        end_date   = payload['end_date']
        leave_type = payload.get('leave_type', 'casual')

        # Affected duty slots
        affected = supabase.table('roster') \
            .select('*') \
            .eq('employee_id', emp_id) \
            .gte('duty_date', start_date) \
            .lte('duty_date', end_date) \
            .eq('status', 'Scheduled') \
            .execute().data

        # Employee designation from Crew DB
        emp = supabase.table('users').select('designation, airport_id') \
            .eq('id', emp_id).single().execute().data
        designation = emp['designation']
        airport_id  = emp['airport_id']

        # Find backup candidates for each affected slot
        recommendations = []
        for slot in affected:
            backups = supabase.table('roster') \
                .select('employee_id, rest_hours_before, shift_start_utc') \
                .eq('duty_date',         slot['duty_date']) \
                .eq('status',            'Standby') \
                .eq('is_backup',         True) \
                .eq('airport_id',        airport_id) \
                .gte('rest_hours_before', 8) \
                .neq('employee_id',      emp_id) \
                .order('rest_hours_before', desc=True) \
                .limit(3).execute().data

            for i, b in enumerate(backups):
                u = supabase.table('users').select('name, designation') \
                    .eq('id', b['employee_id']).single().execute().data
                if u and u['designation'] == designation:
                    recommendations.append({
                        "rank":                 i + 1,
                        "employee_id":          b['employee_id'],
                        "name":                 u['name'],
                        "designation":          u['designation'],
                        "rest_hours_available": b['rest_hours_before'],
                        "duty_date":            slot['duty_date'],
                        "compliance":           "OK",
                        "reason":               f"Rank {i+1} by rest hours"
                    })

        # Insert leave request (Pending — manager must confirm)
        lr = supabase.table('leave_requests').insert({
            "employee_id":    emp_id,
            "leave_type":     leave_type,
            "start_date":     start_date,
            "end_date":       end_date,
            "reason":         payload.get('reason', ''),
            "status":         "Pending",
            "source_chat_id": payload.get('chat_id')
        }).execute().data[0]

        return {
            "response": (
                f"Leave request submitted for {start_date} to {end_date}. "
                f"Your manager has been notified with backup recommendations."
            ),
            "leave_request_id":        lr['id'],
            "affected_duty_slots":     len(affected),
            "backup_recommendations":  recommendations,
            "manager_action_required": True,
            "source":                  "roster_agent"
        }

    # ── EVENT: query ─────────────────────────────────────────
    if event_type == 'query':
        query_text = payload.get('query_text', '')
        airport_id = payload.get('airport_id', '')
        duty_rows  = supabase.table('roster') \
            .select('employee_id, designation, shift_start_utc, shift_end_utc, flight_no') \
            .eq('duty_date',  datetime.utcnow().date().isoformat()) \
            .eq('airport_id', airport_id) \
            .in_('status', ['Scheduled', 'OnDuty']) \
            .execute().data
        # Attach names
        enriched = []
        for row in duty_rows:
            u = supabase.table('users').select('name') \
                .eq('id', row['employee_id']).single().execute().data
            enriched.append({**row, "name": u['name'] if u else 'Unknown'})
        answer = await call_llm(
            system="Answer roster queries based on provided data only.",
            user=f"Question: {query_text}\n\nRoster: {json.dumps(enriched)}"
        )
        return {"response": answer, "data": enriched, "source": "roster_agent"}
```

**Output (leave_request):**
```json
{
  "response": "Leave request submitted for 2026-02-27 to 2026-02-28. Your manager has been notified.",
  "leave_request_id": "uuid",
  "affected_duty_slots": 2,
  "backup_recommendations": [
    { "rank": 1, "name": "Raj Kumar", "rest_hours_available": 14.5, "compliance": "OK" },
    { "rank": 2, "name": "Priya Singh", "rest_hours_available": 11.0, "compliance": "OK" }
  ],
  "manager_action_required": true
}
```

#### `POST /agents/roster/confirm-assignment`
**HTTP Method:** POST | **Auth Required:** Yes (authority_level >= 2)  
**Input:** `{ "leave_request_id": "uuid", "backup_employee_id": "uuid" }`
```python
async def confirm_roster_assignment(payload, user: User) -> dict:
    if user.authority_level < 2:
        raise HTTPException(403, "Only managers can confirm assignments")

    lr = supabase.table('leave_requests').select('*') \
        .eq('id', payload.leave_request_id).single().execute().data

    supabase.table('leave_requests').update({
        "status":             "Approved",
        "backup_assigned_to": payload.backup_employee_id,
        "approved_by":        user.id
    }).eq('id', payload.leave_request_id).execute()

    # Update original employee slots → Leave
    supabase.table('roster').update({"status": "Leave"}) \
        .eq('employee_id', lr['employee_id']) \
        .gte('duty_date', lr['start_date']) \
        .lte('duty_date', lr['end_date']).execute()

    # Assign backup to those slots
    # (fetch affected slots and insert new roster rows for backup)

    return {"message": "Roster updated and backup assigned", "approved": True}
```

#### `GET /agents/roster/availability`
**HTTP Method:** GET | **Auth Required:** Yes  
**Query Params:** `designation`, `date`, `airport_id`  
**Output:** Available + standby staff with rest hours for that designation/date

---

## 11. SLA Crawler — Escalation Engine

Interval-based (not insert-driven). SLA breaches are time-driven, not triggered by a DB insert.

**Runs every:** 60 seconds | **APScheduler job id:** `sla_crawler`

```python
# crawlers/sla_crawler.py
async def crawl_sla_breaches():
    now     = datetime.utcnow()
    now_iso = now.isoformat()

    # Breached = past deadline AND not done
    breached = supabase.table('tasks') \
        .select('*') \
        .not_.in_('status', ['Done']) \
        .lt('sla_deadline_utc', now_iso) \
        .not_.is_('sla_deadline_utc', 'null') \
        .execute().data

    if not breached:
        return

    for task in breached:
        overdue_min   = (now - datetime.fromisoformat(
                            task['sla_deadline_utc'])).total_seconds() / 60
        new_level     = task['escalation_level'] + 1
        next_auth_lvl = min(task['escalation_level'] + 2, 5)
        new_visible   = list(set(task['visible_to_levels'] + [next_auth_lvl]))

        supabase.table('tasks').update({
            "escalation_level":  new_level,
            "visible_to_levels": new_visible,
            "updated_at":        now_iso,
            "audit":             task['audit'] + [{
                "at":          now_iso,
                "by":          "SLACrawler",
                "action":      f"escalated_to_L{next_auth_lvl}",
                "overdue_min": round(overdue_min, 1)
            }]
        }).eq('task_id', task['task_id']).execute()

    # Severe breach (level >= 2) → create escalation OpsCard → re-enters Flow 1
    for task in [t for t in breached if t['escalation_level'] >= 2]:
        existing = supabase.table('ops_cards').select('id') \
            .eq('type', 'escalation') \
            .contains('lineage', {'parent_task_id': task['task_id']}) \
            .execute().data
        if not existing:
            supabase.table('ops_cards').insert({
                "event_id":       f"esc_{uuid4().hex[:8]}",
                "airport_id":     task['airport_id'],
                "type":           "escalation",
                "title":          f"ESCALATION: {task['title']}",
                "summary":        f"Task overdue by {round(overdue_min,0):.0f} min. No action.",
                "priority_score": 99.0,
                "priority_label": "High",
                "urgency_score":  5,
                "authority_level":min(task['escalation_level'] + 1, 5),
                "lineage":        {"parent_task_id": task['task_id'], "by": "SLACrawler"},
                "status":         "unprocessed"   # triggers NOTIFY → Smart Crawler 2
            }).execute()
            # → Smart Crawler 2 picks this up → Router Agent
            # → New task created, visible_to_levels includes L4/L5
```

---

## 12. Dashboard Routes — Kanban, Gantt & Manager

These routes are **read/update only** — they query `tasks`, `activities`, `ops_cards`, `leave_requests`, and `vendor_tickets`. None of these tables have the status enum (that only applies to inbox tables), so these routes are completely unaffected by v4 changes.

### 12.1 Kanban Dashboard (Flow 1 output — flight-wise)

#### `GET /dashboard/tasks`
**HTTP Method:** GET | **Auth Required:** Yes  
**Query Params:** `airport_id` (required), `flight_no` (opt), `priority_label` (opt)

```python
async def get_kanban_tasks(airport_id: str, user: User,
                            flight_no: str = None,
                            priority_label: str = None) -> dict:
    """
    SELECT t.*, oc.type, oc.entities, oc.urgency_score,
           oc.actions_required, oc.confidence, oc.lineage,
           (EXTRACT(EPOCH FROM (t.sla_deadline_utc - NOW())) / 60) AS time_remaining_min
    FROM tasks t
    JOIN ops_cards oc ON t.ops_card_id = oc.event_id
    WHERE t.airport_id = $1
      AND $2 = ANY(t.visible_to_levels)          -- authority gate
      AND ($3 IS NULL OR t.flight_no = $3)
      AND ($4 IS NULL OR t.priority_label = $4)
    ORDER BY t.priority DESC, t.created_at ASC

    Group by status: New, Ack, InProgress, Blocked, Done
    """
```

**Output:**
```json
{
  "airport_id": "DEL_T3",
  "authority_level": 3,
  "kanban": {
    "New": [
      {
        "task_id": "tsk_a1b2c3d4",
        "flight_no": "6E245",
        "title": "Gate Change Required — 6E245",
        "type": "task",
        "priority_label": "High",
        "priority_score": 88.3,
        "sla_deadline_utc": "2026-02-26T07:35:00Z",
        "time_remaining_min": 14.2,
        "escalation_level": 0,
        "labels": ["6E245", "Gate", "High"],
        "entities": { "flightNo": "6E245", "gateFrom": "22", "gateTo": "28" }
      }
    ],
    "Ack":        [],
    "InProgress": [],
    "Blocked":    [],
    "Done":       []
  },
  "counts": { "New": 1, "Ack": 0, "InProgress": 0, "Blocked": 0, "Done": 0 }
}
```

#### `GET /dashboard/tasks/{task_id}` — Single-click detail
**HTTP Method:** GET | **Auth Required:** Yes  
**Output:** Full task + full OpsCard + full audit trail + linked activities

#### `PATCH /dashboard/tasks/{task_id}/ack` — Double-click acknowledge
**HTTP Method:** PATCH | **Auth Required:** Yes
```python
async def acknowledge_task(task_id: str, user: User) -> dict:
    """
    Validate: user.authority_level IN task.visible_to_levels
    Validate: task.status == 'New'

    UPDATE tasks SET
        status     = 'Ack',
        ack_by_id  = user.id,
        ack_at_utc = NOW(),
        updated_at = NOW(),
        audit      = audit || [{ at, by: user.name, action: 'acknowledged' }]
    WHERE task_id = $1
    """
```
**Output:** `{ "task_id": "...", "status": "Ack", "ack_by": "John Doe" }`

#### `PATCH /dashboard/tasks/{task_id}/status`
**HTTP Method:** PATCH | **Auth Required:** Yes  
**Input:** `{ "status": "InProgress" | "Blocked" | "Done", "note": "optional" }`
```python
# Valid transitions:
# Ack        → InProgress | Blocked
# InProgress → Blocked | Done
# Blocked    → InProgress | Done
```

---

### 12.2 Gantt Dashboard (Flow 1 output)

#### `GET /dashboard/activities`
**HTTP Method:** GET | **Auth Required:** Yes  
**Query Params:** `airport_id`, `date` (YYYY-MM-DD), `flight_no` (opt)

```python
async def get_gantt_activities(airport_id: str, date: str,
                                user: User, flight_no: str = None) -> dict:
    """
    SELECT a.*, f.origin, f.destination, f.scheduled_departure, f.status
    FROM activities a
    LEFT JOIN flights f ON a.flight_no = f.flight_no
    WHERE a.airport_id = $1
      AND a.start_utc::date = $2
      AND ($3 IS NULL OR a.flight_no = $3)
    ORDER BY a.start_utc ASC
    """
```

**Output:**
```json
{
  "airport_id": "DEL_T3",
  "date": "2026-02-26",
  "activities": [
    {
      "activity_id": "act_e5f6g7h8",
      "flight_no": "6E245",
      "name": "Gate Change",
      "start_utc": "2026-02-26T07:20:00Z",
      "end_utc": "2026-02-26T07:35:00Z",
      "resource_type": "Gate",
      "resource_id": "G28",
      "state": "Planned",
      "critical_path": true,
      "depends_on": [],
      "flight_details": {
        "origin": "DEL",
        "destination": "BOM",
        "scheduled_departure": "2026-02-26T07:55:00Z"
      }
    }
  ]
}
```

#### `GET /dashboard/ops-card/{event_id}`
**HTTP Method:** GET | **Auth Required:** Yes  
**Output:** Full OpsCard JSON with all entities, lineage, attachments

---

### 12.3 Manager's Dashboard (Flow 2: Roster output)

#### `GET /dashboard/manager/leave-requests`
**HTTP Method:** GET | **Auth Required:** Yes (authority_level >= 2)  
**Query Params:** `airport_id`, `status` (opt: Pending/Approved/Rejected)

```python
async def get_leave_requests(airport_id: str, user: User, status: str = None) -> dict:
    """
    SELECT lr.*, u.name, u.designation, u.department,
           bu.name AS backup_name
    FROM leave_requests lr
    JOIN users u  ON lr.employee_id = u.id
    LEFT JOIN users bu ON lr.backup_assigned_to = bu.id
    WHERE u.airport_id = $1
      AND ($2 IS NULL OR lr.status = $2)
    ORDER BY lr.created_at DESC
    """
```

**Output:**
```json
{
  "leave_requests": [
    {
      "id": "uuid",
      "employee_name": "Amit Sharma",
      "designation": "Ground Staff",
      "leave_type": "emergency",
      "start_date": "2026-02-27",
      "end_date": "2026-02-28",
      "status": "Pending",
      "backup_recommendations": [
        { "rank": 1, "name": "Raj Kumar", "rest_hours_available": 14.5 }
      ]
    }
  ]
}
```

#### `GET /dashboard/manager/roster`
**HTTP Method:** GET | **Auth Required:** Yes (authority_level >= 2)  
**Query Params:** `airport_id`, `date`  
**Output:** Full daily roster — duty slots, backup assignments, leave status for all staff

#### `GET /dashboard/escalations`
**HTTP Method:** GET | **Auth Required:** Yes  
**Output:** Tasks with `escalation_level > 0` visible to this user's authority level, sorted by `escalation_level DESC`

#### `POST /dashboard/tasks/{task_id}/escalate` — Manual escalation
**HTTP Method:** POST | **Auth Required:** Yes  
**Input:** `{ "reason": "No response from gate control for 15 minutes" }`  
Same logic as SLA Crawler but human-initiated: expands `visible_to_levels` by one authority level, increments `escalation_level`, appends audit entry.

---

### 12.4 QAgent Chat History

#### `GET /chat/session/{session_id}`
**HTTP Method:** GET | **Auth Required:** Yes  
**Description:** Returns the full message + response history for one chat session.
```python
"""
SELECT id, raw_content, response, response_source,
       received_at, processed_at, status
FROM chat_inbox
WHERE session_id = $1
  AND sender_id  = user.id
ORDER BY received_at ASC
"""
```

**Output:**
```json
{
  "session_id": "sess_abc123",
  "messages": [
    { "role": "user",      "content": "How many casual leaves do I have?", "received_at": "..." },
    { "role": "assistant", "content": "You have 8 casual leaves remaining...", "source": "hr_database", "processed_at": "..." }
  ]
}
```

---

## 13. Complete Route Registry

> Removed in v4: `/orchestration/route-ops` and `/orchestration/route-chat` — routing logic now lives inline inside Smart Crawlers 2 and 3.

| # | Method | Route | Auth | Flow | Description |
|---|--------|-------|------|------|-------------|
| 1 | POST | `/auth/login` | No | — | Login, get JWT |
| 2 | POST | `/auth/logout` | Yes | — | Invalidate session |
| 3 | GET | `/auth/me` | Yes | — | Current user |
| 4 | POST | `/ingress/message` | Yes | **Flow 1** | Operational message → MSG DB → NOTIFY |
| 5 | POST | `/ingress/chat` | Yes | **Flow 2** | QAgent query → Chat DB → NOTIFY |
| 6 | POST | `/agents/summarizer/process` | Yes | Flow 1 | Summarizer: msg → OpsCard (testable) |
| 7 | POST | `/agents/router/process` | Yes | Flow 1 | Router: OpsCard → Task + Activity (testable) |
| 8 | POST | `/agents/query/process` | Yes | Flow 2 | Query Agent (testable) |
| 9 | POST | `/agents/query/chat` | Yes | Flow 2 | Synchronous QAgent chat (bypasses crawler) |
| 10 | POST | `/agents/roster/process` | Yes | Flow 2 | Roster Agent (testable) |
| 11 | POST | `/agents/roster/confirm-assignment` | Yes | Flow 2 | Manager confirms backup assignment |
| 12 | GET | `/agents/roster/availability` | Yes | Flow 2 | Available backup staff for date |
| 13 | POST | `/agents/cabhotel/process` | Yes | Flow 2 | CabHotel Agent (testable) |
| 14 | PATCH | `/agents/cabhotel/ticket/{id}/resolve` | Yes | Flow 2 | Vendor resolves ticket |
| 15 | GET | `/agents/cabhotel/tickets` | Yes | Flow 2 | List vendor tickets |
| 16 | GET | `/dashboard/tasks` | Yes | Flow 1 | Kanban board (flight-wise) |
| 17 | GET | `/dashboard/tasks/{task_id}` | Yes | Flow 1 | Single task detail (single-click) |
| 18 | PATCH | `/dashboard/tasks/{task_id}/ack` | Yes | Flow 1 | Acknowledge task (double-click) |
| 19 | PATCH | `/dashboard/tasks/{task_id}/status` | Yes | Flow 1 | Update task status |
| 20 | GET | `/dashboard/activities` | Yes | Flow 1 | Gantt board |
| 21 | GET | `/dashboard/ops-card/{event_id}` | Yes | Flow 1 | Full OpsCard detail |
| 22 | GET | `/dashboard/escalations` | Yes | Shared | Escalated tasks |
| 23 | POST | `/dashboard/tasks/{task_id}/escalate` | Yes | Shared | Manual escalation |
| 24 | GET | `/dashboard/manager/leave-requests` | Yes | Flow 2 | Manager: leave list |
| 25 | GET | `/dashboard/manager/roster` | Yes | Flow 2 | Manager: daily roster view |
| 26 | GET | `/chat/session/{session_id}` | Yes | Flow 2 | QAgent chat history |
| 27 | GET | `/flights` | Yes | ref | Flights list for airport |
| 28 | GET | `/flights/{flight_no}` | Yes | ref | Single flight detail |
| 29 | GET | `/roster` | Yes | ref | Full roster for date |
| 30 | PATCH | `/roster/{id}` | Yes | ref | Update roster entry |

---

## 14. End-to-End Flow Diagrams

### Flow 1 — OPS Channel Pipeline (v4)
```
═══════════════════════════════════════════════════════════════════════════
 AUTH (both flows)
═══════════════════════════════════════════════════════════════════════════
 User → POST /auth/login { email, password }
   → SELECT users WHERE email=? / bcrypt verify
   → INSERT sessions { token }
   ← { token, authority_level, airport_id }
   Token sent as Bearer header on every subsequent request

═══════════════════════════════════════════════════════════════════════════
 FLOW 1 — INGRESS
═══════════════════════════════════════════════════════════════════════════
 User fills Message Box:
   Selects message_type: task | info | alert | approval | escalation
   Types operational message + optional flight number
   Hits Submit

 → POST /ingress/message { raw_content, message_type, flight_context }
   → INSERT msg_inbox { status: 'unprocessed' }
   → PostgreSQL trigger fires NOTIFY 'msg_inbox_insert'
   ← { msg_id, status: 'queued' }

═══════════════════════════════════════════════════════════════════════════
 SMART CRAWLER 1 (wakes on NOTIFY, 30s fallback sweep)
═══════════════════════════════════════════════════════════════════════════
 asyncpg hears 'msg_inbox_insert' → calls smart_crawler_1()

 RPC lock_msg_batch(20, crawler_id)  ← atomically claims batch
 SELECT only WHERE status='unprocessed' (processed/failed/in_progress skipped)

 FOR EACH message (ONE AT A TIME):
   │
   ├─ status already 'in_progress'? → skip (another instance claimed it)
   │
   ├─ DEDUP: sha256(flight+type+airport+date)
   │         check ops_cards within last 2h → if match → skip, mark processed
   │
   ├─ ENRICH: flight_context?
   │          → SELECT flights WHERE flight_no=? AND date=today
   │          → add origin, destination, gate, stand, etd to entities
   │
   ├─ LLM: extract title, summary, actions_required, entities,
   │       urgency_score, impact, confidence, deadline_utc
   │
   ├─ SCORE: compute_priority() → priority_score → High(≥85)|Medium(≥70)|Low
   │
   ├─ INSERT ops_cards { status: 'unprocessed' }
   │         → fires NOTIFY 'ops_cards_insert' → wakes Smart Crawler 2
   │
   └─ UPDATE msg_inbox SET status='processed'  ← IMMEDIATE, this record only
      Exception: SET status='failed', retry_count++, continue to next record

═══════════════════════════════════════════════════════════════════════════
 SMART CRAWLER 2 (wakes on NOTIFY, 30s fallback sweep)
═══════════════════════════════════════════════════════════════════════════
 asyncpg hears 'ops_cards_insert' → calls smart_crawler_2()

 RPC lock_ops_batch(20, crawler_id)  ← priority_score DESC (urgent first)

 FOR EACH OpsCard (ONE AT A TIME):
   │
   ├─ INLINE ROUTING (replaces /orchestration/route-ops):
   │   All types {task|alert|info|approval|escalation}
   │   → router_agent_process(card)
   │       ├─ SLA lookup → sla_deadline_utc
   │       ├─ determine_visibility(urgency, authority) → [1,2,3]
   │       ├─ INSERT tasks { status:'New', priority, sla_deadline }
   │       └─ If etd/eta in entities:
   │            INSERT activities { start, end, resource, critical_path }
   │
   └─ UPDATE ops_cards SET status='processed', routed_to='router_agent'
      Exception: SET status='failed', retry_count++, continue

═══════════════════════════════════════════════════════════════════════════
 FRONTEND — KANBAN + GANTT
═══════════════════════════════════════════════════════════════════════════
 GET /dashboard/tasks?airport_id=DEL_T3
   ← Kanban buckets: New/Ack/InProgress/Blocked/Done
   ← Sorted by priority_score DESC within each bucket
   ← Only tasks WHERE user.authority_level IN visible_to_levels
   ← time_remaining_min computed from sla_deadline_utc

 Single-click  → GET /dashboard/tasks/{id}  → full detail + OpsCard
 Double-click  → PATCH /dashboard/tasks/{id}/ack
 Status change → PATCH /dashboard/tasks/{id}/status

 GET /dashboard/activities?airport_id=DEL_T3&date=2026-02-26
   ← Gantt: activities ordered by start_utc, depends_on, critical_path

═══════════════════════════════════════════════════════════════════════════
 SLA CRAWLER (every 60s — interval-based)
═══════════════════════════════════════════════════════════════════════════
 SELECT tasks WHERE sla_deadline_utc < NOW() AND status ≠ 'Done'

 FOR EACH breached task:
   overdue_min   = now - sla_deadline_utc
   new_visible   = visible_to_levels ∪ { min(escalation_level + 2, 5) }
   escalation_level++
   UPDATE tasks SET escalation_level, visible_to_levels, audit entry

   If escalation_level >= 2:
     INSERT ops_cards { type='escalation', status='unprocessed' }
     → fires NOTIFY → Smart Crawler 2 → Router Agent
     → New task now visible to L4/L5 authority
```

### Flow 2 — QAgent / Chat Pipeline (v4)
```
═══════════════════════════════════════════════════════════════════════════
 FLOW 2 — INGRESS
═══════════════════════════════════════════════════════════════════════════
 User opens QAgent chat:
   (Optional) selects query_type: general_query | leave | cab | hotel
   Types question or request
   Hits Send

 → POST /ingress/chat { raw_content, query_type, session_id }
   → INSERT chat_inbox { status: 'unprocessed' }
   → PostgreSQL trigger fires NOTIFY 'chat_inbox_insert'
   ← { chat_id, status: 'queued' }

 Alternative (synchronous — no crawler):
 → POST /agents/query/chat { user_message, conversation_history }
   → query_agent_process() called directly
   ← { response } immediately in same HTTP response

═══════════════════════════════════════════════════════════════════════════
 SMART CRAWLER 3 (wakes on NOTIFY, 30s fallback sweep)
═══════════════════════════════════════════════════════════════════════════
 asyncpg hears 'chat_inbox_insert' → calls smart_crawler_3()

 RPC lock_chat_batch(30, crawler_id)

 FOR EACH chat message (ONE AT A TIME):
   │
   ├─ INLINE ROUTING (replaces /orchestration/route-chat):
   │   query_type = msg.query_type OR auto_classify(raw_content)
   │   │
   │   ├─ 'general_query' → query_agent_process()
   │   │     │
   │   │     ├─ intent='leave_balance'  → SELECT leave_balances
   │   │     ├─ intent='leave_apply'    → llm_extract_params
   │   │     │                            → roster_agent_process()
   │   │     ├─ intent='policy_lookup'  → RAG hr_documents FTS → LLM
   │   │     ├─ intent='roster_query'   → roster_agent_process()
   │   │     └─ intent='general'        → RAG + LLM
   │   │
   │   ├─ 'leave' → roster_agent_process(event_type='leave_request')
   │   │     ├─ SELECT roster (affected duty slots from Crew DB)
   │   │     ├─ SELECT backup (same designation, is_backup=TRUE,
   │   │     │  rest_hours >= 8h, ORDER BY rest_hours DESC)
   │   │     ├─ INSERT leave_requests { status:'Pending' }
   │   │     └─ Returns recommendations → Manager's Dashboard
   │   │
   │   └─ 'cab' | 'hotel' → cabhotel_agent_process()
   │         ├─ LLM extracts details from raw_content
   │         ├─ SELECT vendor (role='vendor', airport_id)
   │         ├─ INSERT vendor_tickets { status:'Open' }
   │         └─ Returns ticket_id → Vendor Dashboard
   │
   └─ UPDATE chat_inbox SET status='processed', response=agent_result
      Exception: SET status='failed', retry_count++, continue

═══════════════════════════════════════════════════════════════════════════
 FRONTEND — QAGENT WINDOW + MANAGER DASHBOARD
═══════════════════════════════════════════════════════════════════════════
 QAgent window polls:
 GET /chat/session/{session_id}
   ← Full message + response history for this session

 Manager dashboard:
 GET /dashboard/manager/leave-requests?status=Pending
   ← Pending leave requests with backup_recommendations[]
 Manager approves:
 POST /agents/roster/confirm-assignment
   { leave_request_id, backup_employee_id }
   → UPDATE leave_requests SET status='Approved'
   → UPDATE roster: original → 'Leave', backup → 'Scheduled'
```

---

## 15. Project Structure & Stack

```
aerocore_poc/
├── main.py                      # FastAPI app + lifespan (NOTIFY listeners + scheduler)
├── config.py                    # Settings via python-dotenv
├── db.py                        # Supabase client singleton (supabase-py)
│
├── middleware/
│   └── auth.py                  # JWT verify_token middleware
│
├── routes/                      # HTTP route handlers only — no business logic
│   ├── auth.py                  # /auth/*
│   ├── ingress.py               # /ingress/message + /ingress/chat
│   ├── dashboard.py             # /dashboard/* + /chat/session/*
│   ├── agents.py                # /agents/* (testable wrappers around agent fns)
│   ├── flights.py               # /flights/*
│   └── roster_ref.py            # /roster/*
│   # NOTE: routes/orchestration.py DOES NOT EXIST in v4
│
├── agents/                      # Pure Python functions — no HTTP, no state
│   ├── summarizer.py            # summarizer_process()
│   ├── router.py                # router_agent_process()
│   ├── query.py                 # query_agent_process(), detect_query_intent()
│   ├── roster.py                # roster_agent_process(), confirm_assignment()
│   └── cabhotel.py              # cabhotel_agent_process()
│
├── crawlers/                    # Smart Crawlers — own full routing logic
│   ├── listener.py              # asyncpg LISTEN setup + channel → crawler mapping
│   ├── msg_crawler.py           # Smart Crawler 1: MSG DB → Summarizer
│   ├── ops_crawler.py           # Smart Crawler 2: OPS DB → Router (inline)
│   ├── chat_crawler.py          # Smart Crawler 3: Chat DB → Agents (inline)
│   ├── routing.py               # route_ops_card_inline() + route_chat_inline()
│   │                            # + auto_classify()
│   └── sla_crawler.py           # Interval-based SLA breach + escalation
│
├── utils/
│   ├── priority.py              # compute_priority(), compute_time_left()
│   ├── llm.py                   # call_llm() — Anthropic SDK wrapper
│   ├── hashing.py               # dedup sha256 helpers
│   └── intent.py                # detect_query_intent() helpers
│
└── models/
    └── schemas.py               # All Pydantic I/O models
```

```
# requirements.txt
fastapi==0.111.0
uvicorn[standard]==0.29.0
supabase==2.4.0                  # Supabase HTTP client (for all DB operations)
asyncpg==0.29.0                  # Direct Postgres connection for LISTEN/NOTIFY
python-jose[cryptography]==3.3.0
bcrypt==4.1.2
apscheduler==3.10.4              # Fallback sweeps + SLA crawler
anthropic==0.25.0                # LLM SDK
pydantic==2.7.0
python-dotenv==1.0.1
httpx==0.27.0
```

```
# .env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
SUPABASE_DB_URL=postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres

SECRET_KEY=your-jwt-secret-key
LLM_API_KEY=your-anthropic-api-key
LLM_MODEL=claude-sonnet-4-20250514

# Crawler config
MSG_BATCH_SIZE=20
OPS_BATCH_SIZE=20
CHAT_BATCH_SIZE=30
CRAWLER_FALLBACK_SWEEP_SEC=30    # interval fallback (primary = NOTIFY)
SLA_CRAWLER_INTERVAL_SEC=60
```

---

*AEROCORE Technical Specification v4 FINAL — POC Edition*
*Smart Crawler Architecture: Orchestration Removed, Trigger-Based, Per-Record Commit*
*Stack: Python (FastAPI) + Supabase PostgreSQL + asyncpg + APScheduler + Anthropic*
