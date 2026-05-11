# AEROCORE Backend - Render Deployment Guide

## ✅ Pre-Deployment Checklist

- [ ] Requirements.txt has all dependencies (including `pydantic-settings`)
- [ ] `.env` file is properly configured locally
- [ ] Git repository is committed and pushed
- [ ] Render account created at https://render.com
- [ ] GitHub repository connected to Render

---

## 🚀 Step-by-Step Deployment Instructions

### Step 1: Prepare Your Repository

Make sure all changes are committed to git:

```bash
git add -A
git commit -m "Fix: Add pydantic-settings to requirements for Render deployment"
git push origin main
```

### Step 2: Create a New Web Service on Render

1. **Go to Render Dashboard**: https://dashboard.render.com
2. **Click "New +"** → Select **"Web Service"**
3. **Connect to your GitHub repository**:
   - Select your GitHub account
   - Choose the repository containing this backend
   - Select the branch (typically `main`)

### Step 3: Configure the Web Service

Fill in the following settings:

| Setting                 | Value                                                |
| ----------------------- | ---------------------------------------------------- |
| **Name**          | `aerocore-backend`                                 |
| **Environment**   | `Python 3`                                         |
| **Region**        | `Oregon` (or closest to you)                       |
| **Branch**        | `main`                                             |
| **Build Command** | `pip install -r requirements.txt`                  |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Plan**          | `Free` (can upgrade later)                         |

### Step 4: Set Environment Variables

⚠️ **CRITICAL**: Add all required environment variables in Render dashboard.

Click **"Environment"** and add these variables:

```
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

> **Security Note**: Consider using Render's secret variables feature or environment groups for sensitive keys.

### Step 5: Deploy

1. **Click "Deploy"** - Render will automatically:

   - Clone your repository
   - Install dependencies from `requirements.txt`
   - Start your application
2. **Monitor the deployment** in the Logs tab:

   - Watch for build progress
   - Check for any error messages
   - Verify the app starts successfully

### Step 6: Access Your API

Once deployed, your API will be available at:

```
https://aerocore-backend.onrender.com
```

Test the deployment:

```bash
curl https://aerocore-backend.onrender.com/
```

---

## 🔧 Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'pydantic_settings'`

**Solution**: ✅ Already fixed - `pydantic-settings` added to `requirements.txt`

### Issue: `ModuleNotFoundError` for other packages

**Steps**:

1. Add missing package to `requirements.txt` with version
2. Commit and push to git
3. Redeploy (Render will auto-redeploy on git push)

### Issue: Application starts but returns 500 errors

**Check**:

1. Environment variables are set correctly in Render dashboard
2. Supabase connection string is valid
3. API keys are correct
4. Check logs in Render dashboard

### Issue: Database connection fails

**Steps**:

1. Verify `SUPABASE_DB_URL` is correct
2. Check Supabase project is active
3. Verify IP whitelist settings in Supabase (if applicable)
4. Test connection locally with same credentials

### Free Tier Limitations

- Spins down after 15 minutes of inactivity
- Limited to 100 hours/month
- Single instance only
- Recommended upgrade to **Starter ($7/month)** for production

---

## 📋 Additional Configuration Options

### Custom Domain (Optional)

1. In Render dashboard, go to your service
2. Click "Settings" → "Custom Domain"
3. Add your domain (requires DNS configuration)

### Auto-Deploy on Git Push

This is enabled by default. Simply push to your branch:

```bash
git push origin main  # Render auto-redeploys
```

### View Real-Time Logs

```bash
# In Render dashboard, click your service → "Logs" tab
# Or use Render CLI:
render logs aerocore-backend
```

---

## 🎯 Post-Deployment

1. **Test API endpoints**:

   ```bash
   curl https://aerocore-backend.onrender.com/api/auth/login
   curl https://aerocore-backend.onrender.com/api/ingress/messages
   ```
2. **Monitor in production**:

   - Check Render dashboard regularly
   - Set up error alerts if needed
   - Monitor Supabase connection metrics
3. **Keep dependencies updated**:

   ```bash
   pip install --upgrade-all  # Update all packages
   pip freeze > requirements.txt  # Update requirements.txt
   git push  # Auto-redeploys on Render
   ```

---

## 📚 Useful Render Commands (CLI)

Install Render CLI:

```bash
npm install -g render
```

Login and manage services:

```bash
render login
render ps  # List all services
render logs aerocore-backend  # View logs
render restart aerocore-backend  # Restart service
```

---

## ✨ What Was Fixed for Render

1. ✅ Added `pydantic-settings==2.2.0` to requirements.txt
2. ✅ Added `gunicorn==21.2.0` for production WSGI server (optional)
3. ✅ Created `render.yaml` with proper configuration
4. ✅ Configured uvicorn with port binding for Render

Your deployment should now work! 🎉
