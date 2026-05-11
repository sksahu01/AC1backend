"""
Authentication routes: login, logout, me
"""
from fastapi import APIRouter, HTTPException, Request, status, Depends
from jose import jwt
from datetime import datetime, timedelta
import bcrypt
from app.db import db
from app.config import settings
from app.models.schemas import LoginPayload, LoginResponse, User
from app.middleware.auth import verify_token
from uuid import UUID

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginPayload):
    """
    Login endpoint. Returns JWT token and user info.
    POST /auth/login { email, password }
    """
    # 1. Fetch user from Supabase
    result = db.table("users").select("*").eq("email", payload.email).eq("is_active", True).execute()

    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_data = result.data[0]

    # 2. Verify password
    try:
        if not bcrypt.checkpw(
            payload.password.encode(), 
            user_data["password_hash"].encode()
        ):
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 3. Generate JWT
    exp = datetime.utcnow() + timedelta(hours=12)
    token = jwt.encode(
        {
            "user_id": user_data["id"],
            "email": user_data["email"],
            "name": user_data["name"],
            "role": user_data["role"],
            "authority_level": user_data["authority_level"],
            "airport_id": user_data["airport_id"],
            "department": user_data.get("department"),
            "designation": user_data.get("designation"),
            "employee_id": user_data.get("employee_id"),
            "exp": exp
        },
        settings.secret_key,
        algorithm="HS256"
    )

    # 4. Store session in Supabase
    db.table("sessions").insert({
        "user_id": user_data["id"],
        "token": token,
        "expires_at": exp.isoformat(),
        "is_active": True
    }).execute()

    # 5. Return token + user
    user = User(
        id=UUID(user_data["id"]),
        email=user_data["email"],
        name=user_data["name"],
        role=user_data["role"],
        authority_level=user_data["authority_level"],
        airport_id=user_data["airport_id"],
        department=user_data.get("department"),
        designation=user_data.get("designation"),
        employee_id=user_data.get("employee_id"),
        is_active=user_data["is_active"],
        created_at=datetime.fromisoformat(user_data["created_at"].replace("Z", "+00:00"))
    )

    return LoginResponse(token=token, user=user, expires_at=exp)


@router.post("/logout")
async def logout(request: Request):
    """
    Logout endpoint. Invalidates session.
    POST /auth/logout (requires Bearer token)
    """
    user = await verify_token(request)
    
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "")

    db.table("sessions").update({"is_active": False}).eq("token", token).execute()

    return {"message": "Logged out successfully"}


@router.get("/me", response_model=User)
async def get_current_user(request: Request):
    """
    Get current authenticated user.
    GET /auth/me (requires Bearer token)
    """
    return await verify_token(request)
