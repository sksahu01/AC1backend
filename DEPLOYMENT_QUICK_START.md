# 🚀 AEROCORE Backend - Render Deployment Quick Start

## What Was Fixed

✅ **Missing Dependency**: Added `pydantic-settings==2.2.0` to requirements.txt  
✅ **Render Configuration**: Created `render.yaml` with proper settings  
✅ **Deployment Guide**: Complete step-by-step instructions  
✅ **Health Check**: Verification script to ensure readiness  
✅ **Environment Template**: `.env.example` for reference  

---

## 📋 Quick Deploy in 3 Steps

### 1️⃣ Verify Everything is Ready
```bash
python3 check_deployment_ready.py
```

### 2️⃣ Commit and Push
```bash
git add -A
git commit -m "feat: Prepare backend for Render deployment"
git push origin main
```

### 3️⃣ Deploy on Render
1. Go to https://dashboard.render.com
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repo
4. Enter these settings:

| Field | Value |
|-------|-------|
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

5. **Set Environment Variables** (from `.env.example`)
6. Click **Deploy**

---

## 🔑 Required Environment Variables

Copy these from your `.env` file to Render dashboard:

```
SUPABASE_URL
SUPABASE_KEY
SUPABASE_DB_URL
SECRET_KEY
LLM_API_KEY
LLM_MODEL
MSG_BATCH_SIZE
OPS_BATCH_SIZE
CHAT_BATCH_SIZE
CRAWLER_FALLBACK_SWEEP_SEC
SLA_CRAWLER_INTERVAL_SEC
```

---

## 📚 Documentation Files

- **RENDER_DEPLOYMENT.md** - Complete deployment guide with troubleshooting
- **.env.example** - Environment variable template
- **check_deployment_ready.py** - Pre-deployment verification script
- **deploy.sh** - Automated deployment setup script (Linux/Mac)

---

## ✅ Verification Checklist

Before deploying:

- [ ] Run `python3 check_deployment_ready.py` and all checks pass
- [ ] `.env` file is properly configured locally
- [ ] Repository is committed and pushed to GitHub
- [ ] All environment variables are documented
- [ ] Render dashboard shows the service starting

---

## 🎯 Expected Result

Once deployed, your API will be available at:
```
https://aerocore-backend.onrender.com
```

Test it:
```bash
curl https://aerocore-backend.onrender.com/
```

---

## ⚠️ Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: pydantic_settings` | ✅ Already fixed in requirements.txt |
| 500 errors at startup | Check environment variables in Render dashboard |
| Database connection fails | Verify SUPABASE_DB_URL is correct and Supabase project is active |
| Free tier spins down | Upgrade to Starter plan ($7/month) for production |

---

## 📞 Support

- Render Docs: https://render.com/docs
- FastAPI Docs: https://fastapi.tiangolo.com
- Supabase Docs: https://supabase.com/docs

---

**Ready to deploy? Run `python3 check_deployment_ready.py` to get started! 🚀**
