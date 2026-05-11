#!/usr/bin/env python3
"""
Pre-Deployment Health Check Script
Verifies all dependencies and configuration are ready for Render deployment.
"""
import sys
import subprocess
from pathlib import Path


def check_python_version():
    """Check Python version is 3.11+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 11):
        print(f"❌ Python version {version.major}.{version.minor} detected")
        print("   Required: Python 3.11 or higher")
        return False
    print(f"✅ Python version: {version.major}.{version.minor}.{version.micro}")
    return True


def check_requirements_file():
    """Check if requirements.txt exists and contains critical dependencies"""
    req_file = Path("requirements.txt")
    if not req_file.exists():
        print("❌ requirements.txt not found")
        return False
    
    with open(req_file, "r") as f:
        content = f.read()
    
    critical_packages = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "pydantic-settings",  # THIS WAS THE MISSING ONE
        "supabase",
        "asyncpg",
        "python-jose"
    ]
    
    missing = []
    for pkg in critical_packages:
        if pkg.lower() not in content.lower():
            missing.append(pkg)
    
    if missing:
        print(f"❌ Missing packages in requirements.txt: {', '.join(missing)}")
        return False
    
    print("✅ All critical packages in requirements.txt:")
    for pkg in critical_packages:
        print(f"   • {pkg}")
    return True


def check_env_file():
    """Check if .env file exists with required variables"""
    env_file = Path(".env")
    if not env_file.exists():
        print("⚠️  .env file not found (will need to set env vars in Render dashboard)")
        return True
    
    required_vars = [
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "SUPABASE_DB_URL",
        "SECRET_KEY",
        "LLM_API_KEY"
    ]
    
    with open(env_file, "r") as f:
        content = f.read()
    
    missing = []
    for var in required_vars:
        if f"{var}=" not in content:
            missing.append(var)
    
    if missing:
        print(f"⚠️  Missing env variables: {', '.join(missing)}")
        print("   Will need to set these in Render dashboard")
        return True
    
    print("✅ .env file found with required variables")
    return True


def check_main_files():
    """Check if main app files exist"""
    files_to_check = [
        "app/main.py",
        "app/config.py",
        "app/db.py",
        "app/routes/auth.py",
        "app/routes/ingress.py",
        "requirements.txt",
        "Dockerfile"
    ]
    
    missing = []
    for file in files_to_check:
        if not Path(file).exists():
            missing.append(file)
    
    if missing:
        print(f"❌ Missing files: {', '.join(missing)}")
        return False
    
    print("✅ All main app files present")
    return True


def check_render_config():
    """Check if render.yaml exists"""
    if not Path("render.yaml").exists():
        print("⚠️  render.yaml not found (created during preparation)")
        return True
    
    print("✅ render.yaml configuration found")
    return True


def check_git_status():
    """Check if repository is clean"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True
        )
        
        if result.stdout.strip():
            print("⚠️  Uncommitted changes detected:")
            print("   Run: git add -A && git commit -m 'Prepare for Render deployment'")
            print("   Then: git push origin main")
            return False
        
        print("✅ Git repository clean and ready")
        return True
    except subprocess.CalledProcessError:
        print("⚠️  Git not available or not a git repository")
        return True


def main():
    """Run all health checks"""
    print("\n" + "=" * 70)
    print("AEROCORE Backend - Render Deployment Health Check")
    print("=" * 70 + "\n")
    
    checks = [
        ("Python Version", check_python_version),
        ("Requirements File", check_requirements_file),
        ("Environment File", check_env_file),
        ("Main App Files", check_main_files),
        ("Render Configuration", check_render_config),
        ("Git Status", check_git_status),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n[{len(results) + 1}/{len(checks)}] {name}")
        print("-" * 70)
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Error during check: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print(f"\n{passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 Your backend is ready for Render deployment!")
        print("\nNext steps:")
        print("1. git push origin main")
        print("2. Go to https://dashboard.render.com")
        print("3. Create new Web Service and connect your GitHub repo")
        print("4. Set environment variables (see RENDER_DEPLOYMENT.md)")
        print("5. Click Deploy\n")
        return 0
    else:
        print("\n⚠️  Please fix the failed checks before deploying\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
