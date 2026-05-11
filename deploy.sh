#!/bin/bash
# Quick Render Deployment Script

set -e

echo "🚀 AEROCORE Backend - Render Deployment Setup"
echo "=============================================="
echo ""

# Step 1: Verify Python version
echo "✓ Checking Python version..."
python3 --version | grep -E "3\.1[1-9]|3\.[2-9][0-9]" > /dev/null || {
    echo "❌ Python 3.11+ required"
    exit 1
}

# Step 2: Check requirements.txt
echo "✓ Checking requirements.txt..."
if ! grep -q "pydantic-settings" requirements.txt; then
    echo "❌ pydantic-settings missing from requirements.txt"
    exit 1
fi

# Step 3: Check .env file
echo "✓ Checking .env configuration..."
if [ ! -f .env ]; then
    echo "⚠️  .env file not found - will set in Render dashboard"
fi

# Step 4: Run health check
echo "✓ Running deployment health checks..."
python3 check_deployment_ready.py || exit 1

# Step 5: Prepare git
echo ""
echo "📝 Preparing git repository..."
if [ -n "$(git status --porcelain)" ]; then
    echo "   Uncommitted changes detected:"
    git status --short
    echo ""
    echo "   Committing changes..."
    git add -A
    git commit -m "chore: Prepare for Render deployment - add pydantic-settings and config"
fi

# Step 6: Push to git
echo ""
echo "🔄 Pushing to GitHub..."
git push origin main

# Step 7: Next steps
echo ""
echo "✅ Repository ready for deployment!"
echo ""
echo "📋 NEXT STEPS:"
echo "   1. Go to https://dashboard.render.com"
echo "   2. Click 'New +' → 'Web Service'"
echo "   3. Connect your GitHub repository"
echo "   4. Configure:"
echo "      - Branch: main"
echo "      - Build Command: pip install -r requirements.txt"
echo "      - Start Command: uvicorn app.main:app --host 0.0.0.0 --port \$PORT"
echo "   5. Add Environment Variables (see .env.example)"
echo "   6. Click 'Deploy'"
echo ""
echo "📚 See RENDER_DEPLOYMENT.md for detailed instructions"
echo ""
