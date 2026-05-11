# AEROCORE v4 — Backend Implementation

Agentic AI Operations Platform for airport operations management.

**Stack:** Python 3.11+ | FastAPI | Supabase PostgreSQL | asyncpg | APScheduler | Anthropic Claude

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- PostgreSQL (via Supabase)
- Anthropic API key (Claude access)

### 2. Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Or use virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate (Windows)
pip install -r requirements.txt
```

### 3. Configuration

Edit `.env` file with your credentials:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
SUPABASE_DB_URL=postgresql://postgres:password@db.your-project.supabase.co:5432/postgres
SECRET_KEY=your-jwt-secret-key-min-32-chars
LLM_API_KEY=your-anthropic-api-key
LLM_MODEL=claude-sonnet-4-20250514
```

### 4. Database Setup

In Supabase SQL Editor, run the contents of `database/init.sql`:

```sql
-- Copy entire init.sql and execute in Supabase
-- Creates all 14 tables, indexes, triggers, and RPCs
```

### 5. Run Backend

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Server runs at: `http://localhost:8000`

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│              FRONTEND (React/Vite)                      │
│  Message Box (Flow 1)  │  QAgent/QBOT (Flow 2)          │
└────────────┬───────────────────────────────┬────────────┘
             │                               │
    POST /ingress/message       POST /ingress/chat
             │                               │
             ▼                               ▼
   ┌──────────────────────┐    ┌──────────────────────┐
   │   msg_inbox (MSG DB) │    │  chat_inbox (Chat DB)│
   │   status=unprocessed │    │  status=unprocessed │
   └────────┬─────────────┘    └─────────┬────────────┘
            │ NOTIFY                      │ NOTIFY
            │ msg_inbox_insert            │ chat_inbox_insert
            ▼                             ▼
   ┌──────────────────────┐    ┌──────────────────────┐
   │  Smart Crawler 1     │    │  Smart Crawler 3     │
   │  (Flow 1 — MSG)      │    │  (Flow 2 — Chat)     │
   │  ↓ Summarizer        │    │  ↓ Auto-classify     │
   └────────┬─────────────┘    │  ↓ Inline routing    │
            │ INSERT            │  ├→ Query Agent      │
            │ ops_cards         │  ├→ Roster Agent     │
            │ NOTIFY            │  └→ CabHotel Agent   │
            ▼                   │                      │
   ┌──────────────────────┐    │                      │
   │  ops_cards (OPS DB)  │    │ Write response back  │
   │  status=unprocessed  │    │ to chat_inbox        │
   └────────┬─────────────┘    └─────────────────────┘
            │ NOTIFY
            │ ops_cards_insert
            ▼
   ┌──────────────────────┐
   │  Smart Crawler 2     │
   │  (Flow 1 — OPS)      │
   │  ↓ Router inline     │
   │  ↓ Create tasks      │
   │  ↓ Create activities │
   └──────────────────────┘
            │ INSERT
            ▼
   ┌──────────────────────────────────┐
   │  tasks + activities              │
   │  (Kanban + Gantt)                │
   │  Visible to: managers + workers  │
   └──────────────────────────────────┘

             SLA Crawler (60s)
             └→ Escalate breaches
             └→ Create escalation OpsCards
```

---

## File Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app + lifespan
│   ├── config.py                  # Settings from .env
│   ├── db.py                      # Supabase client
│   │
│   ├── models/
│   │   └── schemas.py             # All Pydantic models
│   │
│   ├── middleware/
│   │   └── auth.py                # JWT verification
│   │
│   ├── routes/
│   │   ├── auth.py                # /auth/* endpoints
│   │   └── ingress.py             # /ingress/* endpoints
│   │
│   ├── agents/                    # Pure functions (no HTTP)
│   │   ├── summarizer.py          # OpsCard creation
│   │   ├── router.py              # Task + activity creation
│   │   ├── query.py               # General queries + RAG
│   │   ├── roster.py              # Leave + roster queries
│   │   └── cabhotel.py            # Ticket creation
│   │
│   ├── crawlers/                  # Smart crawlers + routing
│   │   ├── listener.py            # asyncpg LISTEN setup
│   │   ├── msg_crawler.py         # Smart Crawler 1 (MSG)
│   │   ├── ops_crawler.py         # Smart Crawler 2 (OPS)
│   │   ├── chat_crawler.py        # Smart Crawler 3 (Chat)
│   │   ├── routing.py             # Inline routing functions
│   │   └── sla_crawler.py         # SLA escalation (60s)
│   │
│   └── utils/
│       ├── priority.py            # Priority scoring
│       ├── llm.py                 # Anthropic API wrapper
│       ├── intent.py              # Query classification
│       └── hashing.py             # Dedup hashing
│
├── requirements.txt               # Python dependencies
├── .env                          # Configuration (DO NOT COMMIT)
└── database/
    └── init.sql                  # Full schema + triggers
```

---

## Key Flows

### Flow 1: Operational Message → Dashboard

1. User submits via **Message Box** (web)
2. **POST /ingress/message** → insert into `msg_inbox`
3. PostgreSQL trigger fires NOTIFY `msg_inbox_insert`
4. **Smart Crawler 1** wakes (or 30s sweep)
5. Calls **Summarizer Agent** inline:
   - Dedup check
   - Flight enrichment
   - LLM extraction
   - Priority scoring
6. Creates `ops_cards` → NOTIFY
7. **Smart Crawler 2** wakes:
   - Calls **Router Agent** inline
   - Creates `tasks` (Kanban) + `activities` (Gantt)
8. Frontend polls **GET /dashboard/tasks** → displays on Kanban

### Flow 2: QAgent Query → Response

1. User types in **QAgent sidebar** (web)
2. **POST /ingress/chat** → insert into `chat_inbox`
3. PostgreSQL trigger fires NOTIFY `chat_inbox_insert`
4. **Smart Crawler 3** wakes:
   - Auto-classifies query type
   - Routes to appropriate agent:
     - **Query Agent** (general questions, leave balance, policies)
     - **Roster Agent** (leave requests, duty roster)
     - **CabHotel Agent** (cab/hotel tickets)
5. Response written back to `chat_inbox`
6. Frontend polls **GET /chat/session/{session_id}** → displays in chat window

---

## API Endpoints

### Authentication

- `POST /auth/login` — Get JWT token
- `POST /auth/logout` — Invalidate session
- `GET /auth/me` — Current user info

### Ingress

- `POST /ingress/message` — Submit operational message → Flow 1
- `POST /ingress/chat` — Submit QAgent query → Flow 2

### Agent Testing (Testable Directly)

- `POST /agents/summarizer/process` — Test summarizer
- `POST /agents/router/process` — Test router
- `POST /agents/query/process` — Test query agent
- `POST /agents/query/chat` — Direct chat (sync, no crawler)
- `POST /agents/roster/process` — Test roster agent
- `POST /agents/roster/confirm-assignment` — Manager confirms leave
- `POST /agents/cabhotel/process` — Test cab/hotel agent

### Dashboard (Read-only)

- `GET /dashboard/tasks` — Kanban board
- `GET /dashboard/tasks/{task_id}` — Single task detail
- `PATCH /dashboard/tasks/{task_id}/ack` — Acknowledge task
- `PATCH /dashboard/tasks/{task_id}/status` — Update task status
- `GET /dashboard/activities` — Gantt board
- `GET /dashboard/manager/leave-requests` — Pending leaves
- `GET /dashboard/manager/roster` — Daily roster
- `GET /chat/session/{session_id}` — Chat history

### Health

- `GET /health` — Server status

---

## Crawler Triggers

### Primary: PostgreSQL NOTIFY/LISTEN

- **Smart Crawler 1** listens on `msg_inbox_insert`
- **Smart Crawler 2** listens on `ops_cards_insert`
- **Smart Crawler 3** listens on `chat_inbox_insert`
- Wakes within ~300ms of INSERT

### Fallback: APScheduler (every 30s)

- Crawlers also run on 30s interval
- Catches any missed NOTIFYs
- No work if no unprocessed rows

### SLA Crawler (every 60s)

- Detects breached tasks
- Escalates visibility to higher authority levels
- Creates escalation OpsCards for severe breaches

---

## Environment Variables

```env
# Supabase
SUPABASE_URL=...               # Your Supabase project URL
SUPABASE_KEY=...               # Service role key (not anon)
SUPABASE_DB_URL=...            # PostgreSQL connection string (for asyncpg LISTEN)

# Auth
SECRET_KEY=...                 # 32+ char random key for JWT signing

# LLM
LLM_API_KEY=...                # Anthropic API key
LLM_MODEL=claude-sonnet-4-20250514

# Crawlers
MSG_BATCH_SIZE=20              # Messages per batch (Smart Crawler 1)
OPS_BATCH_SIZE=20              # OpsCards per batch (Smart Crawler 2)
CHAT_BATCH_SIZE=30             # Chats per batch (Smart Crawler 3)
CRAWLER_FALLBACK_SWEEP_SEC=30  # Fallback sweep interval
SLA_CRAWLER_INTERVAL_SEC=60    # SLA check interval

# App
ENVIRONMENT=development        # development | production
DEBUG=True                      # Enable debug logging
```

---

## Testing

### Unit Tests (TODO)

```bash
# Run with pytest
pytest tests/
```

### Manual Testing

#### Test Auth

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@airline.com","password":"password"}'
```

#### Test Message Ingress

```bash
curl -X POST http://localhost:8000/ingress/message \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_content": "Gate change needed for 6E245",
    "message_type": "task",
    "flight_context": "6E245"
  }'
```

#### Test Chat Ingress

```bash
curl -X POST http://localhost:8000/ingress/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_content": "How many leaves do I have?",
    "query_type": "general_query",
    "session_id": "sess_123"
  }'
```

---

## Troubleshooting

### Crawlers not waking

1. Check PostgreSQL LISTEN connection in logs
2. Verify Supabase DB URL is correct (with direct DB connection, not HTTP)
3. Check RPC permissions (`lock_msg_batch`, etc.)
4. Verify NOTIFY triggers exist on tables

### LLM calls failing

1. Check `LLM_API_KEY` and `LLM_MODEL` in `.env`
2. Verify Anthropic API is accessible
3. Check token usage and rate limits

### Task visibility issues

1. Verify user `authority_level` in `users` table
2. Check `visible_to_levels` array in `tasks` table
3. Confirm SLA escalation is updating levels

---

## Production Deployment

### Before Deployment

- [ ] Set `DEBUG=False` in `.env`
- [ ] Use strong, random `SECRET_KEY`
- [ ] Restrict CORS origins (not `*`)
- [ ] Set up proper logging (e.g., Sentry)
- [ ] Configure database backups (Supabase)
- [ ] Set up monitoring/alerts
- [ ] Test scalability with multiple crawler instances
- [ ] Review security: RLS, VPC, encryption

### Docker Deployment

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Documentation References

- **AEROCORE Spec v4:** See `Docs/AEROCORE_Technical_Spec_v4_FINAL.md`
- **Database Schema:** See `database/init.sql`
- **API Routes:** Swagger UI at `http://localhost:8000/docs`

---

## Support & Contribution

For issues or feature requests, see the technical specification document for requirements and architecture details.

---

*AEROCORE v4 — POC Edition*  
*Smart Crawler Architecture · NOTIFY/LISTEN Triggers · Per-Record Commits · v4 Final*
