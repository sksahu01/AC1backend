"""
Summarizer Agent — Flow 1
Processes raw operational messages into structured OpsCards.
Called inline by Smart Crawler 1.
"""
import json
import logging
from datetime import datetime, timedelta
from app.db import db
from app.utils.llm import call_llm_json
from app.utils.hashing import compute_dedup_hash
from app.utils.priority import compute_priority, get_priority_label
import uuid

logger = logging.getLogger("aerocore.summarizer")

SUMMARIZER_SYSTEM_PROMPT = """
You are an operational summarizer for an airport operations control center.
Your task is to extract structured information from raw operational messages.

Return ONLY a valid JSON object with these exact keys:
- title (str, max 10 words, action-oriented)
- summary (str, 1-2 sentences, what + why)
- actions_required (list of strings)
- entities (dict with: flightNo, origin, destination, gateFrom, gateTo, stand, 
  ownerRole, requester, eta, etd, resource — include all found in message, 
  or {} if none)
- urgency_score (int 1-5, where 5 is highest)
- impact (int 1-5, where 5 is highest)
- confidence (float 0-1, 1 being certain)
- deadline_utc (ISO string or null if no deadline)
- policy_flags (list of strings, empty if no policies)

Example:
{
  "title": "Gate Change Required — 6E245",
  "summary": "Flight 6E245 needs immediate gate reassignment from G22 to G28 due to stand conflict.",
  "actions_required": ["Notify Gate Control", "Update FIDS", "Inform Ground Handling"],
  "entities": {"flightNo": "6E245", "gateFrom": "22", "gateTo": "28", "etd": "2026-02-26T07:55:00Z"},
  "urgency_score": 4,
  "impact": 5,
  "confidence": 0.9,
  "deadline_utc": "2026-02-26T07:35:00Z",
  "policy_flags": ["ground_handling_sop", "gate_reassignment"]
}
"""


async def summarizer_process(msg: dict) -> dict | None:
    """
    Main summarizer function. Called inline by Smart Crawler 1.
    
    Args:
        msg: Message dict from msg_inbox table
        
    Returns:
        OpsCard dict ready for insertion, or None if duplicate
    """

    logger.info(f"[SUMMARIZER] Processing message {msg['id']}")

    # ─────────────────────────────────────────────────────────
    # STEP 1: DEDUPLICATION
    # ─────────────────────────────────────────────────────────
    today = datetime.utcnow().date().isoformat()
    dedup_hash = compute_dedup_hash(
        msg.get("flight_context", ""),
        msg["message_type"],
        msg["airport_id"],
        today
    )

    # Check for existing OpsCards with same hash within last 2 hours
    existing = (
        db.table("ops_cards")
        .select("id")
        .eq("dedup_hash", dedup_hash)
        .gte("created_at", (datetime.utcnow() - timedelta(hours=2)).isoformat())
        .execute()
        .data
    )

    if existing:
        logger.info(f"[SUMMARIZER] Duplicate detected for {msg['id']} — suppressing")
        return None

    # ─────────────────────────────────────────────────────────
    # STEP 2: FLIGHT ENRICHMENT
    # ─────────────────────────────────────────────────────────
    flight_details = {}
    if msg.get("flight_context"):
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()
        today_end = datetime.utcnow().replace(hour=23, minute=59, second=59).isoformat()

        f_result = (
            db.table("flights")
            .select("*")
            .eq("flight_no", msg["flight_context"])
            .eq("airport_id", msg["airport_id"])
            .gte("scheduled_departure", today_start)
            .lte("scheduled_departure", today_end)
            .limit(1)
            .execute()
        )

        if f_result.data:
            f = f_result.data[0]
            flight_details = {
                "origin": f.get("origin"),
                "destination": f.get("destination"),
                "gate": f.get("gate_assigned"),
                "stand": f.get("stand_assigned"),
                "etd": f.get("scheduled_departure"),
                "eta": f.get("scheduled_arrival"),
                "flightStatus": f.get("status"),
                "aircraftType": f.get("aircraft_type")
            }
            logger.info(f"[SUMMARIZER] Enriched with flight data: {f.get('flight_no')}")

    # ─────────────────────────────────────────────────────────
    # STEP 3: LLM CALL
    # ─────────────────────────────────────────────────────────
    prompt = f"""
Operational message from {msg['sender_name']} ({msg['sender_role']}, Authority Level {msg['authority_level']}).
Type: {msg['message_type']}
Message: {msg['raw_content']}

Flight data from database: {json.dumps(flight_details, default=str)}
Received at: {msg['received_at']}

Extract and structure this operational information into JSON.
"""

    try:
        parsed = await call_llm_json(SUMMARIZER_SYSTEM_PROMPT, prompt)
        logger.info(f"[SUMMARIZER] LLM parsed: {parsed.get('title')}")
    except Exception as e:
        logger.error(f"[SUMMARIZER] LLM call failed: {e}")
        raise

    # ─────────────────────────────────────────────────────────
    # STEP 4: PRIORITY SCORING
    # ─────────────────────────────────────────────────────────
    deadline = parsed.get("deadline_utc")
    if deadline:
        time_left = (
            datetime.fromisoformat(deadline.replace("Z", "+00:00"))
            - datetime.fromisoformat(msg["received_at"].replace("Z", "+00:00"))
        ).total_seconds() / 60
    else:
        time_left = 120  # default

    score = compute_priority(
        time_left_min=time_left,
        urgency_score=parsed.get("urgency_score", 3),
        authority_level=msg["authority_level"],
        impact=parsed.get("impact", 3),
        confidence=parsed.get("confidence", 0.8)
    )
    label = get_priority_label(score)

    logger.info(f"[SUMMARIZER] Priority score: {score} ({label})")

    # ─────────────────────────────────────────────────────────
    # STEP 5: BUILD OPS CARD
    # ─────────────────────────────────────────────────────────
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    event_id = f"evt_{ts}_{msg['airport_id']}"

    ops_card = {
        "event_id": event_id,
        "airport_id": msg["airport_id"],
        "type": msg["message_type"],
        "title": parsed.get("title", "Operational Event"),
        "summary": parsed.get("summary", msg["raw_content"][:200]),
        "actions_required": parsed.get("actions_required", []),
        "entities": {**parsed.get("entities", {}), **flight_details},
        "urgency_score": parsed.get("urgency_score", 3),
        "priority_score": score,
        "priority_label": label,
        "deadline_utc": deadline,
        "authority_level": msg["authority_level"],
        "impact": parsed.get("impact", 3),
        "confidence": parsed.get("confidence", 0.8),
        "dedup_hash": dedup_hash,
        "policy_flags": parsed.get("policy_flags", []),
        "lineage": {
            "origMsgId": str(msg["id"]),
            "senderName": msg["sender_name"],
            "senderRole": msg["sender_role"],
            "agent": "Summarizer@v1.0",
            "createdAt": datetime.utcnow().isoformat()
        },
        "source_msg_id": str(msg["id"]),
        "routing_status": "pending",
        "status": "unprocessed"
    }

    logger.info(f"[SUMMARIZER] OpsCard created: {event_id}")
    return ops_card
