"""
CabHotel Agent — Flow 2
Handles cab and hotel ticket creation and routing to vendors.
Called inline by Smart Crawler 3.
"""
import json
import logging
from datetime import datetime, timedelta
from uuid import uuid4
from app.db import db
from app.utils.llm import call_llm_json

logger = logging.getLogger("aerocore.cabhotel")


async def cabhotel_agent_process(payload: dict) -> dict:
    """
    Main CabHotel Agent function. Extracts details, finds vendor, creates ticket.
    Called inline by Smart Crawler 3.
    
    Args:
        payload: Dict with ticket_type, requester_id, airport_id, query_text
        
    Returns:
        Dict with response, ticket_id, vendor_name, etc.
    """
    ticket_type = payload.get("ticket_type", "cab")
    requester_id = payload.get("requester_id")
    airport_id = payload.get("airport_id")
    query_text = payload.get("query_text", "")
    chat_id = payload.get("chat_id")

    logger.info(f"[CABHOTEL] Processing {ticket_type} request: {query_text[:60]}")

    # ─────────────────────────────────────────────────────────
    # STEP 1: EXTRACT DETAILS (LLM)
    # ─────────────────────────────────────────────────────────
    extraction_system = f"""
Extract details from this {ticket_type} request and return ONLY valid JSON.
For cab: {{ pickup_location, pickup_time, passengers, return_time (optional), notes }}
For hotel: {{ hotel_name (optional), check_in, check_out, rooms, special_requests (optional) }}
Use ISO datetime format for times.
"""

    try:
        details_raw = await call_llm_json(extraction_system, query_text)
        details = details_raw
        logger.info(f"[CABHOTEL] Extracted: {details}")
    except Exception as e:
        logger.error(f"[CABHOTEL] LLM extraction failed: {e}")
        details = {"raw_request": query_text}

    # ─────────────────────────────────────────────────────────
    # STEP 2: FIND ASSIGNED VENDOR
    # ─────────────────────────────────────────────────────────
    try:
        vendors = (
            db.table("users")
            .select("id, name")
            .eq("role", "vendor")
            .eq("airport_id", airport_id)
            .eq("is_active", True)
            .limit(5)
            .execute()
            .data
        )

        # Simple round-robin or first available
        vendor_id = vendors[0]["id"] if vendors else None
        vendor_name = vendors[0]["name"] if vendors else "Unassigned"

        logger.info(f"[CABHOTEL] Vendor: {vendor_name}")
    except Exception as e:
        logger.error(f"[CABHOTEL] Vendor lookup failed: {e}")
        vendor_id = None
        vendor_name = "Unassigned"

    # ─────────────────────────────────────────────────────────
    # STEP 3: CREATE VENDOR TICKET
    # ─────────────────────────────────────────────────────────
    ticket_id = f"vt_{uuid4().hex[:8]}"
    sla_deadline = (datetime.utcnow() + timedelta(minutes=30)).isoformat()

    try:
        db.table("vendor_tickets").insert({
            "ticket_id": ticket_id,
            "ticket_type": ticket_type,
            "requester_id": str(requester_id),
            "vendor_id": str(vendor_id) if vendor_id else None,
            "details": details,
            "status": "Open",
            "sla_deadline_utc": sla_deadline,
            "source_chat_id": str(chat_id) if chat_id else None
        }).execute()

        logger.info(f"[CABHOTEL] Ticket created: {ticket_id}")
    except Exception as e:
        logger.error(f"[CABHOTEL] Failed to create ticket: {e}")
        raise

    # ─────────────────────────────────────────────────────────
    # STEP 4: RETURN RESPONSE
    # ─────────────────────────────────────────────────────────
    return {
        "response": (
            f"Your {ticket_type} request (Ticket: {ticket_id}) has been sent to "
            f"{vendor_name}. Expected response within 30 minutes."
        ),
        "ticket_id": ticket_id,
        "vendor_name": vendor_name,
        "sla_deadline": sla_deadline,
        "data": details,
        "source": "cabhotel_agent",
        "action_taken": True
    }


async def resolve_vendor_ticket(ticket_id: str, user_id: str, resolution_notes: str) -> dict:
    """
    Vendor resolves a ticket.
    Called via PATCH /agents/cabhotel/ticket/{ticket_id}/resolve
    
    Args:
        ticket_id: Ticket ID to resolve
        user_id: Vendor's user ID
        resolution_notes: Resolution details
    """
    logger.info(f"[CABHOTEL] Resolving ticket: {ticket_id}")

    try:
        # Verify ownership
        ticket = (
            db.table("vendor_tickets")
            .select("*")
            .eq("ticket_id", ticket_id)
            .single()
            .execute()
            .data
        )

        if not ticket:
            return {"error": "Ticket not found"}

        if str(ticket.get("vendor_id")) != str(user_id):
            return {"error": "Unauthorized: not the assigned vendor"}

        # Update ticket
        db.table("vendor_tickets").update({
            "status": "Resolved",
            "resolution_notes": resolution_notes,
            "resolved_at": datetime.utcnow().isoformat()
        }).eq("ticket_id", ticket_id).execute()

        logger.info(f"[CABHOTEL] Ticket resolved: {ticket_id}")
        return {"message": "Ticket resolved", "ticket_id": ticket_id}

    except Exception as e:
        logger.error(f"[CABHOTEL] Resolve failed: {e}")
        return {"error": str(e)}
