# AEROCORE Frontend-Backend Integration Guide

## Overview

This guide walks you through testing the complete integration between the AEROCORE frontend and backend. The integration tests verify that both services work together seamlessly.

**Quick Start:**
```bash
# Run all integration tests
python integration_tests.py
```

---

## Table of Contents

1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Running Integration Tests](#running-integration-tests)
4. [Test Categories](#test-categories)
5. [Manual Testing](#manual-testing)
6. [Troubleshooting](#troubleshooting)
7. [Common Flows](#common-flows)

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND (React/Vite)                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ • Login Page                                          │  │
│  │ • Dashboard (KanbanView)                              │  │
│  │ • Workspace (Chat, Messages)                          │  │
│  │ • Real-time Updates (Supabase)                        │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬─────────────────────────────────────────┘
                     │ HTTP Requests
                     │ ws:// WebSocket (Supabase)
┌────────────────────▼─────────────────────────────────────────┐
│                    BACKEND (FastAPI)                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ /auth          → Authentication (JWT tokens)         │  │
│  │ /ingress       → Message & Chat ingestion           │  │
│  │ /dashboard     → Task queries & updates              │  │
│  │ /agents        → Smart processing                    │  │
│  │ /crawlers      → Background jobs                     │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬─────────────────────────────────────────┘
                     │ SQL Queries
                     │ NOTIFY/LISTEN Events
┌────────────────────▼─────────────────────────────────────────┐
│                  DATABASE (PostgreSQL)                       │
│  • messages, chats, tasks, activities                       │
│  • users, flights, leave_requests, vendor_tickets           │
└─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Backend Setup

✅ **Already installed:**
- FastAPI 0.136.1
- Uvicorn 0.46.0
- Pydantic 2.13.4
- All required agents and crawlers

✅ **Environment:**
- `.env` file configured with DATABASE_URL, ANTHROPIC_API_KEY
- Python 3.11+ (or Docker with Python 3.11)
- PostgreSQL running (locally or via Docker)

### Frontend Setup

✅ **Already installed:**
- React + TypeScript
- Vite bundler
- Tailwind CSS
- Supabase client

✅ **Environment:**
- `.env.local` with VITE_SUPABASE_URL and VITE_SUPABASE_KEY
- Node.js 18+
- npm or yarn

### Testing Tools

Just installed:
- `requests` — For HTTP API calls
- `pytest` — For test execution (already in requirements.txt)

---

## Running Integration Tests

### Option 1: Quick Test (Backend Only)

Test if the backend endpoints exist and respond:

```bash
# From workspace root
cd backend
python ../integration_tests.py
```

**Expected Output:**
```
[PASS] Backend Health Check
[PASS] Swagger UI Available
[PASS] Login Endpoint Exists
[PASS] Message Ingress Endpoint
[PASS] Chat Ingress Endpoint
[PASS] Frontend Structure
[PASS] API Contract Verification
[PASS] Both Projects Exist
```

**Time:** ~5 seconds

### Option 2: Full Integration Test (Both Services)

Start both services, then run tests:

#### Terminal 1: Start Backend

```bash
# Option A: Docker
docker compose up --build

# Option B: Local Python 3.11
cd backend
source .venv311/Scripts/activate  # Windows: .venv311\Scripts\activate
python -m uvicorn app.main:app --reload --port 8000
```

**Wait for:** `Application startup complete`

#### Terminal 2: Start Frontend

```bash
cd frontend
npm install  # if needed
npm run dev
```

**Wait for:** `VITE v5.x.x ready in Xs`

#### Terminal 3: Run Tests

```bash
python integration_tests.py
```

**Expected Output:**
```
════════════════════════════════════════════════════════════════════════════════
                   AEROCORE FRONTEND-BACKEND INTEGRATION TESTS
════════════════════════════════════════════════════════════════════════════════

[PASS] Backend Health Check
[PASS] Swagger UI Available
[PASS] Login Endpoint Exists
[PASS] Message Ingress Endpoint
[PASS] Chat Ingress Endpoint
[PASS] Frontend Structure
[PASS] API Contract Verification
[PASS] Both Projects Exist

SUCCESS RATE: 100.0%
```

**Time:** ~10 seconds (if both services running)

---

## Test Categories

### Category 1: Backend Health

| Test | What It Checks | Expected Result |
|------|----------------|-----------------|
| **Backend Health Check** | Can reach `/health` endpoint | Status 200 |
| **Swagger UI Available** | API documentation loaded | Status 200 + swagger HTML |
| **API Docs Endpoint** | `/docs` and `/redoc` available | Status 200 |

**Why:** Confirms backend is running and accepting requests.

### Category 2: Authentication

| Test | What It Checks | Expected Result |
|------|----------------|-----------------|
| **Login Endpoint** | POST `/auth/login` responds | Status 200 or 401 (not 500) |
| **Token Generation** | JWT token issued on success | Token format: `eyJ...` |
| **Auth Headers** | API accepts Bearer tokens | Authorization headers work |

**Why:** Frontend must authenticate to access protected endpoints.

### Category 3: Message Ingestion

| Test | What It Checks | Expected Result |
|------|----------------|-----------------|
| **Message Endpoint** | POST `/ingress/message` exists | Status 200, 201, or 422 |
| **Chat Endpoint** | POST `/ingress/chat` exists | Status 200, 201, or 422 |
| **Request Validation** | Invalid payloads rejected | Status 422 (validation error) |

**Why:** Frontend sends user input via these endpoints.

### Category 4: Frontend Structure

| Test | What It Checks | Expected Result |
|------|----------------|-----------------|
| **Package.json** | Frontend dependencies defined | File exists and valid JSON |
| **Vite Config** | Build configuration present | File exists and parseable |
| **TypeScript Types** | Type definitions included | tsconfig.json exists |

**Why:** Frontend must be properly configured to build.

### Category 5: API Contract

| Test | What It Checks | Expected Result |
|------|----------------|-----------------|
| **Endpoints Accessible** | Frontend can call backend APIs | All endpoints respond |
| **Request Format** | APIs accept expected payload format | JSON payloads work |
| **Response Format** | APIs return expected response format | JSON responses valid |

**Why:** Frontend and backend must speak the same "language".

### Category 6: Project Compatibility

| Test | What It Checks | Expected Result |
|------|----------------|-----------------|
| **Both Projects Exist** | frontend/ and backend/ folders present | Both folders found |
| **Configuration Files** | Both have config (.env, vite.config) | All files exist |
| **Dependencies Defined** | Both have package.json/requirements.txt | Dependency files exist |

**Why:** Confirms complete project structure.

---

## Manual Testing

### Scenario 1: User Login

**Step 1: Frontend Form**
```
User opens login page
Enters email: "test@airline.com"
Enters password: "test123"
Clicks "Login"
```

**Step 2: Backend Processing**
```
Frontend → POST /auth/login
         → {"email": "test@airline.com", "password": "test123"}

Backend → Validates credentials
       → Generates JWT token
       → Returns: {"token": "eyJ...", "user": {...}}
```

**Step 3: Frontend Response**
```
Frontend receives token
Saves to localStorage
Redirects to dashboard
Includes token in all future requests: Authorization: Bearer eyJ...
```

**Expected Duration:** < 500ms

---

### Scenario 2: Send Task Message

**Step 1: Frontend Form**
```
User types: "Gate change needed for 6E245 from 22 to 28"
Selects flight: "6E245"
Clicks "Send"
```

**Step 2: Backend Processing**
```
Frontend → POST /ingress/message
        → {
             "raw_content": "Gate change needed...",
             "message_type": "task",
             "flight_context": "6E245"
           }

Backend → Summarizer Agent
       → Extract key info: gate change, flight, gates
       → Router Agent
       → Create task and activity
       → Store in database
       → Emit NOTIFY event
```

**Step 3: Frontend Display**
```
Frontend receives response with task ID
Task appears in Kanban board (OPS column)
Real-time listener updates dashboard
```

**Expected Duration:** < 2 seconds

---

### Scenario 3: Send Chat Query

**Step 1: Frontend Chat**
```
User types: "How many casual leaves do I have?"
Clicks "Send"
```

**Step 2: Backend Processing**
```
Frontend → POST /ingress/chat
        → {
             "raw_content": "How many casual leaves do I have?",
             "session_id": "sess_123"
           }

Backend → Query Agent
       → Detect intent: "leave_balance"
       → Call Roster Agent
       → Query database or LLM
       → Generate response
```

**Step 3: Frontend Display**
```
Frontend receives response
Message appears in chat feed
User sees answer: "You have 5 casual leaves remaining"
```

**Expected Duration:** < 3 seconds

---

## Troubleshooting

### Backend Won't Start

**Error:** `Address already in use`

**Solution:**
```bash
# Find process on port 8000
lsof -i :8000

# Kill it
kill -9 <PID>

# Try again
python -m uvicorn app.main:app --port 8000
```

**Alternative:** Use a different port:
```bash
python -m uvicorn app.main:app --port 8001
# Then update integration_tests.py: backend_url="http://localhost:8001"
```

---

### Frontend Won't Build

**Error:** `Module not found: 'react'`

**Solution:**
```bash
cd frontend
rm -rf node_modules
npm install
npm run dev
```

---

### Tests Show "Connection Refused"

**Error:** `Cannot connect to localhost:8000`

**Solution:**
1. Verify backend is running: `curl http://localhost:8000/health`
2. If not, start backend: `docker compose up` or `python -m uvicorn ...`
3. Wait 5 seconds for startup
4. Run tests again

---

### Authentication Fails

**Error:** `Status 401 - Unauthorized`

**Possible Causes:**
- User doesn't exist in database
- Password incorrect
- Database not initialized

**Solution:**
```bash
# Reinitialize database
psql -U postgres -d aerocore -f database/init.sql

# Try test credentials
# Email: test@airline.com
# Password: test123
```

---

### Message Ingestion Fails

**Error:** `Status 422 - Validation Error`

**Solution:**
Check request payload includes required fields:
```python
{
    "raw_content": "...",      # Required: message text
    "message_type": "task",    # Required: task or general
    "flight_context": "6E245"  # Required: flight number
}
```

---

## Common Flows

### Flow 1: Complete Login → Dashboard Load

```
1. Frontend loads (http://localhost:5173)
2. User clicks "Login" button
3. Frontend sends: POST /auth/login
4. Backend returns JWT token
5. Frontend saves token to localStorage
6. Frontend redirects to /dashboard
7. Frontend calls: GET /dashboard/tasks
8. Backend returns: [Task, Task, Task...]
9. Dashboard displays tasks in Kanban view
10. Frontend subscribes to real-time updates via Supabase
```

**Expected Time:** 1-2 seconds

---

### Flow 2: Message → Kanban Update

```
1. User in workspace sends message: "Gate change needed for 6E245"
2. Frontend: POST /ingress/message
3. Backend Summarizer: Extract entities
4. Backend Router: Create Task
5. Database: INSERT tasks, activities
6. Database: NOTIFY ops_tasks
7. Backend listener: Receive NOTIFY
8. Database: LISTEN for changes
9. Frontend: Real-time subscription updates
10. Kanban board: New card appears in OPS column
```

**Expected Time:** < 2 seconds

---

### Flow 3: Chat Query → Answer

```
1. User in chat types: "How many casual leaves?"
2. Frontend: POST /ingress/chat
3. Backend Query Agent: Detect intent
4. Backend Roster Agent: Query leave balance
5. Database: SELECT casual_leaves FROM leave_requests
6. Response: "You have 5 casual leaves"
7. Frontend receives response
8. Chat displays response
```

**Expected Time:** 1-3 seconds

---

## Next Steps

After successful integration tests:

1. **Performance Testing** — Use `curl` or Postman for load testing
2. **E2E Tests** — Use Cypress or Playwright for automated UI tests
3. **Error Handling** — Verify error messages display correctly
4. **Real-time Sync** — Test multiple users updating same task
5. **Production Deployment** — Use Docker for both services

---

## Additional Resources

- **Backend README:** `backend/README.md`
- **Frontend README:** `frontend/README.md`
- **API Documentation:** `backend/README.md` (API Registry section)
- **Technical Specification:** `Docs/AEROCORE_Technical_Spec_v4_FINAL.md`
- **Test Results:** `backend/TEST_RESULTS.md`

---

**Last Updated:** May 11, 2026  
**Version:** 1.0  
**Maintainer:** AEROCORE Team
