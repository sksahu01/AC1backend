# AEROCORE Backend — Start Guide (Step-by-Step)

## Quick Start (Choose ONE Method)

### 🐳 Method 1: Docker (FASTEST - Recommended)

**Prerequisites:** Docker Desktop installed + WSL2 enabled

**Steps:**

```powershell
# 1. Open PowerShell in backend folder
cd C:\Users\think\Downloads\BackUp_AeroCore\BackUp_AeroCore\backend

# 2. Update .env with your Supabase credentials (OPTIONAL - use defaults for testing)
# Edit .env and replace:
#   SUPABASE_URL, SUPABASE_KEY, SUPABASE_DB_URL, LLM_API_KEY

# 3. Build and run
docker compose up --build

# 4. Wait for: "Uvicorn running on http://0.0.0.0:8000"
# 5. Open browser: http://localhost:8000/docs
# 6. Stop with: Ctrl+C
```

**Time:** 2-5 minutes (first run: 5 min, subsequent: 30 sec)

**Logs:**

```powershell
# In another terminal, watch logs
docker compose logs -f
```

---

### 🐍 Method 2: Python 3.11 Locally

**Prerequisites:** Python 3.11 installed (from python.org or Windows Store)

**Steps:**

```powershell
# 1. Open PowerShell in backend folder
cd C:\Users\think\Downloads\BackUp_AeroCore\BackUp_AeroCore\backend

# 2. Create venv with Python 3.11
C:\Users\think\AppData\Local\Programs\Python\Python311\python.exe -m venv .venv311

# 3. Activate venv
.\.venv311\Scripts\Activate.ps1

# 4. Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 5. Run backend
python -m uvicorn app.main:app --reload

# 6. Wait for: "Uvicorn running on http://127.0.0.1:8000"
# 7. Open browser: http://localhost:8000/docs
# 8. Stop with: Ctrl+C
```

**Time:** 5-10 minutes (first run: 10 min for pip install, subsequent: 5 sec)

---

### 💻 Method 3: Current Python 3.13 (With Workaround)

**Current Status:** Some packages not fully built for Python 3.13

**Available (tested working):**

- ✅ Core logic tests pass (priority, intent, hashing)
- ✅ Config and auth modules work
- ❌ Cannot run full FastAPI app (needs supabase + asyncpg)

**If you want to test with current venv:**

```powershell
# Already installed - run tests only
cd C:\Users\think\Downloads\BackUp_AeroCore\BackUp_AeroCore\backend
.\.venv\Scripts\python.exe test_backend.py

# Results: 48.6% pass rate (logic tests pass, DB tests need supabase)
```

---

## Verify It's Running

### 1. Health Check

```powershell
# From any terminal/PowerShell
curl http://localhost:8000/health
# Expected response: {"status":"ok"}
```

### 2. API Docs

```
http://localhost:8000/docs
http://localhost:8000/redoc
```

Opens Swagger UI in browser — all endpoints documented

### 3. Test Login (No credentials needed for now)

```powershell
curl -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/json" `
  -d '{\"email\":\"test@airline.com\",\"password\":\"test123\"}'

# Expected: {"detail":"Invalid credentials"} or {"token":"...", "user":{...}}
# (depends on whether test user exists in DB)
```

---

## Environment Variables Explained

**File:** `.env` in backend folder

```env
# === SUPABASE (Database) ===
SUPABASE_URL=https://addyoururl.supabase.co/rest/v1/
# URL to your Supabase project REST API
# Get from: Supabase Dashboard → Settings → API

SUPABASE_KEY=your_service_role_key_here
# Service role key (private - keep secret in production!)
# Get from: Supabase Dashboard → Settings → API → Service Role

SUPABASE_DB_URL=postgresql://postgres:[password]@db.yoururl.supabase.co:5432/postgres
# Direct PostgreSQL connection for asyncpg (LISTEN/NOTIFY)
# Format: postgresql://user:password@host:port/dbname
# PASSWORD is your Supabase password set during project creation

# === AUTHENTICATION ===
SECRET_KEY=your-jwt-secret-key-min-32-chars
# Used to sign JWT tokens - CHANGE THIS IN PRODUCTION!
# Min 32 characters, any random string

# === LLM (Anthropic Claude) ===
LLM_API_KEY=gemini_api_key_here
# Get from: console.anthropic.com → API Keys
# Need active Anthropic account + billing

LLM_MODEL=gemini-2.0-flash
# Claude model name - current options:
#   - claude-sonnet-4-20250514 (recommended)
#   - claude-opus-4-1-20250805
#   - claude-3-5-sonnet-20241022

# === CRAWLER CONFIG ===
MSG_BATCH_SIZE=20          # Messages per crawler batch
OPS_BATCH_SIZE=20          # OpsCards per crawler batch
CHAT_BATCH_SIZE=30         # Chats per crawler batch
CRAWLER_FALLBACK_SWEEP_SEC=30  # Fallback sweep interval (seconds)
SLA_CRAWLER_INTERVAL_SEC=60    # SLA check interval (seconds)
```

### How to Get Values

#### Supabase:

1. Go to https://supabase.com → create account → new project
2. Settings → API → Copy URL and Service Role key
3. For DB URL: use password you set + project ref from URL

#### Anthropic:

1. Go to https://console.anthropic.com
2. Create account → API keys
3. Create new key → copy to LLM_API_KEY

#### SECRET_KEY:

```powershell
# Generate random 32-char string:
[System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((New-Guid).ToString() + (New-Guid).ToString())) | Select-Object -First 32
```

---

## What Happens After Startup

### 1. Lifespan Events

```
[INFO] Starting asyncpg LISTEN connections (3 channels)
[INFO] Registering Smart Crawler triggers
[INFO] APScheduler starting (4 jobs)
   - msg_crawler sweep: 30s interval
   - ops_crawler sweep: 30s interval  
   - chat_crawler sweep: 30s interval
   - sla_crawler: 60s interval
[INFO] FastAPI app ready on http://0.0.0.0:8000
```

### 2. Available Endpoints

#### Authentication

```
POST /auth/login           - JWT login
POST /auth/logout          - Invalidate session
GET  /auth/me              - Get current user
```

#### Data Ingestion

```
POST /ingress/message      - Submit operational message
POST /ingress/chat         - Submit QAgent query
```

#### Utility

```
GET  /health               - Server status
GET  /docs                 - Swagger API docs
GET  /redoc                - ReDoc API docs
```

#### Dashboard (TODO)

```
GET  /dashboard/tasks      - Kanban tasks
GET  /dashboard/activities - Gantt activities
GET  /dashboard/escalations - Escalated tasks
```

---

## Troubleshooting

### ❌ Port 8000 already in use

```powershell
# Kill process using port 8000
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Or use different port
python -m uvicorn app.main:app --reload --port 8001
```

### ❌ "ModuleNotFoundError: No module named 'supabase'"

**Solution:** Use Docker or Python 3.11 method (see above)

### ❌ "SUPABASE_URL not set"

**Solution:** Update .env file with real Supabase credentials

### ❌ Docker daemon not running

```powershell
# On Windows, start Docker Desktop application
# Or restart WSL: wsl --shutdown
```

### ❌ Slow startup (>30 seconds)

- First run of Docker: normal (building image)
- First run of Python: normal (compiling packages)
- Subsequent runs should be instant

### ✅ "Uvicorn running on http://0.0.0.0:8000"

**SUCCESS!** Backend is running. Open browser to http://localhost:8000/docs

---

## Next Steps After Backend Starts

### 1. Test API (with curl or Postman)

```powershell
# Save token to variable
$LOGIN = curl -s -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/json" `
  -d '{"email":"test@airline.com","password":"test"}' | ConvertFrom-Json

$TOKEN = $LOGIN.token

# Test protected endpoint
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/auth/me
```

### 2. Deploy Database Schema

```sql
-- In Supabase SQL Editor, run entire init.sql file:
-- (Copy C:\Users\think\Downloads\BackUp_AeroCore\BackUp_AeroCore\backend\database\init.sql)

-- Creates:
-- - 14 tables (users, messages, cards, tasks, etc.)
-- - 3 NOTIFY triggers (msg_inbox, ops_cards, chat_inbox)
-- - 3 atomic lock RPCs (for crawler coordination)
-- - Indexes and constraints
```

### 3. Monitor Crawlers

```powershell
# Check crawler logs
docker compose logs -f aerocore-backend

# Look for patterns:
# "Smart Crawler 1 locked X msgs"
# "Smart Crawler 2 locked X ops_cards"
# "Smart Crawler 3 locked X chats"
```

### 4. Connect Frontend

Frontend can now call:

```
POST http://localhost:8000/auth/login
POST http://localhost:8000/ingress/message
POST http://localhost:8000/ingress/chat
GET  http://localhost:8000/dashboard/tasks
```

---

## Development Tips

### Hot Reload (Local Python)

```powershell
# Run with --reload to auto-restart on file changes
python -m uvicorn app.main:app --reload
```

### Debug Mode

```powershell
# Add to app/main.py
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost"])
```

### View Database

```powershell
# Connect to Supabase in VS Code
# Extension: "Supabase" (official)
# Open database browser and inspect tables
```

---

## Production Deployment

Not covered in this guide, but files are ready:

- ✅ Dockerfile (production-ready)
- ✅ docker-compose.yml
- ✅ Environment variables system
- ⏳ Kubernetes manifests (future)
- ⏳ CI/CD pipeline (future)

For production:

1. Use Dockerfile with Python 3.11 (provided)
2. Set strong SECRET_KEY
3. Use restricted CORS origins
4. Enable HTTPS
5. Set DEBUG=False in .env

---

## Quick Decision Tree

```
Do you have Docker installed?
  ├─ YES → Use Method 1 (Docker) ✅
  └─ NO
      ├─ Want to install Python 3.11?
      │   ├─ YES → Use Method 2 (Python 3.11) ✅
      │   └─ NO → Use Method 3 (Current Python + Tests only) ⏳
```

---

**Ready to go?** Pick a method above and let's start! 🚀

Any issues, check the troubleshooting section or run:

```powershell
.\.venv\Scripts\python.exe test_backend.py  # For logic validation
```

---

Generated: May 11, 2026
