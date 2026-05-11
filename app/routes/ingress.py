"""
Ingress routes for Flow 1 (ops channel) and Flow 2 (QAgent)
POST /ingress/message  — Message Box → msg_inbox
POST /ingress/chat     — QAgent Box → chat_inbox
"""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime
from app.db import db
from app.models.schemas import (
    IngestMessagePayload, IngestMessageResponse,
    IngestChatPayload, IngestChatResponse
)
from app.middleware.auth import verify_token

router = APIRouter(prefix="/ingress", tags=["ingress"])

ALLOWED_MESSAGE_TYPES = {"task", "info", "alert", "approval", "escalation"}
ALLOWED_QUERY_TYPES = {"general_query", "leave", "cab", "hotel"}


@router.post("/message", response_model=IngestMessageResponse)
async def ingest_message(payload: IngestMessagePayload, request: Request):
    """
    POST /ingress/message
    Operational Message Box → msg_inbox (MSG DB)
    
    NOTIFY fires automatically on INSERT → Smart Crawler 1 wakes
    """
    user = await verify_token(request)

    # Validate message_type
    if payload.message_type not in ALLOWED_MESSAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"message_type must be one of {ALLOWED_MESSAGE_TYPES}"
        )

    # Validate raw_content
    if not payload.raw_content.strip():
        raise HTTPException(status_code=400, detail="raw_content cannot be empty")

    # Insert into msg_inbox
    try:
        result = db.table("msg_inbox").insert({
            "sender_id": str(user.id),
            "sender_name": user.name,
            "sender_role": user.role,
            "authority_level": user.authority_level,
            "airport_id": user.airport_id,
            "raw_content": payload.raw_content.strip(),
            "flight_context": payload.flight_context,
            "message_type": payload.message_type,
            "status": "unprocessed",
            "received_at": datetime.utcnow().isoformat()
        }).execute()

        msg_id = result.data[0]["id"] if result.data else None
        return IngestMessageResponse(
            msg_id=msg_id,
            status="queued",
            pipeline="ops_flow",
            received_at=datetime.utcnow()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest message: {str(e)}")


@router.post("/chat", response_model=IngestChatResponse)
async def ingest_chat(payload: IngestChatPayload, request: Request):
    """
    POST /ingress/chat
    QAgent / QBOT query → chat_inbox (Chat DB)
    
    NOTIFY fires automatically on INSERT → Smart Crawler 3 wakes
    """
    user = await verify_token(request)

    # Validate query_type if provided
    if payload.query_type and payload.query_type not in ALLOWED_QUERY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"query_type must be one of {ALLOWED_QUERY_TYPES}"
        )

    # Validate raw_content
    if not payload.raw_content.strip():
        raise HTTPException(status_code=400, detail="raw_content cannot be empty")

    # Insert into chat_inbox
    try:
        result = db.table("chat_inbox").insert({
            "sender_id": str(user.id),
            "sender_name": user.name,
            "sender_role": user.role,
            "airport_id": user.airport_id,
            "raw_content": payload.raw_content.strip(),
            "query_type": payload.query_type,
            "session_id": payload.session_id,
            "conversation_history": payload.conversation_history or [],
            "status": "unprocessed",
            "received_at": datetime.utcnow().isoformat()
        }).execute()

        chat_id = result.data[0]["id"] if result.data else None
        return IngestChatResponse(
            chat_id=chat_id,
            status="queued",
            pipeline="qagent_flow",
            session_id=payload.session_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest chat: {str(e)}")
