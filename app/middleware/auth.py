"""
Authentication middleware and JWT verification
"""
from fastapi import Request, HTTPException, status
from jose import JWTError, jwt
from app.config import settings
from app.models.schemas import User
from datetime import datetime
from uuid import UUID


async def verify_token(request: Request) -> User:
    """
    Extract and verify JWT from Authorization header.
    Raises HTTPException(401) if token is invalid or expired.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header"
        )

    token = auth_header.replace("Bearer ", "")

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )
        return User(
            id=UUID(user_id),
            email=payload.get("email", ""),
            name=payload.get("name", ""),
            role=payload.get("role", ""),
            authority_level=payload.get("authority_level", 1),
            airport_id=payload.get("airport_id", ""),
            department=payload.get("department"),
            designation=payload.get("designation"),
            employee_id=payload.get("employee_id"),
            is_active=True,
            created_at=datetime.utcnow()
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}"
        )
