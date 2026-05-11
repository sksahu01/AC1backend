"""
Routing functions for Smart Crawlers 2 and 3.
These replace the removed /orchestration/route-ops and /orchestration/route-chat endpoints.
"""
import logging
from app.agents.router import router_agent_process
from app.agents.query import query_agent_process
from app.agents.roster import roster_agent_process
from app.agents.cabhotel import cabhotel_agent_process
from app.utils.intent import detect_query_intent

logger = logging.getLogger("aerocore.routing")


# ============================================================================
# ROUTE 1: OpsCard Routing (Flow 1 — Smart Crawler 2)
# ============================================================================

async def route_ops_card_inline(ops_card: dict) -> dict:
    """
    v4: Replaces /orchestration/route-ops entirely.
    All routing logic lives inline in Smart Crawler 2.

    All OpsCard types (task|info|alert|approval|escalation)
    → router_agent_process() → creates tasks + activities
    
    Special case: if entities contain roster-specific keys,
    also invoke roster_agent in parallel.
    """
    logger.info(f"[ROUTING] Route OpsCard {ops_card['event_id']} (type={ops_card['type']})")

    # Main routing: all types use router_agent
    result = await router_agent_process(ops_card)

    # Check for roster-related entities
    entities = ops_card.get("entities", {})
    roster_keys = ["leaveRequest", "staffShortage", "crewGap"]
    if any(k in entities for k in roster_keys):
        logger.info(f"[ROUTING] Roster-related entities detected, invoking roster agent")
        try:
            await roster_agent_process({
                "event_type": "ops_escalation",
                "airport_id": ops_card["airport_id"],
                "query_text": f"OpsCard escalation: {ops_card['summary']}"
            })
        except Exception as e:
            logger.error(f"[ROUTING] Roster agent invocation failed: {e}")

    return {
        "routed_to": "router_agent",
        **result
    }


# ============================================================================
# ROUTE 2: Chat Routing (Flow 2 — Smart Crawler 3)
# ============================================================================

def auto_classify(text: str) -> str:
    """
    Lightweight keyword classifier for query_type when not specified.
    Upgradeable to LLM-based classification.
    """
    t = text.lower()

    # Leave-related
    if any(
        w in t for w in [
            "leave",
            "leaves",
            "casual",
            "sick leave",
            "apply leave",
            "leave balance"
        ]
    ):
        return "leave"

    # Cab/taxi-related
    if any(
        w in t for w in ["cab", "taxi", "pickup", "drop", "vehicle", "transport"]
    ):
        return "cab"

    # Hotel/accommodation-related
    if any(w in t for w in ["hotel", "accommodation", "room", "stay", "check-in"]):
        return "hotel"

    return "general_query"


async def route_chat_inline(chat_msg: dict) -> dict:
    """
    v4: Replaces /orchestration/route-chat entirely.
    Routes chat messages to appropriate agents based on query_type.

    Routing table:
    - 'general_query'  → query_agent_process()
    - None (auto)      → auto_classify() → re-route
    - 'leave'          → roster_agent_process(event_type='leave_request')
    - 'cab' | 'hotel'  → cabhotel_agent_process()
    """
    logger.info(f"[ROUTING] Route chat {chat_msg['id']}")

    query_type = chat_msg.get("query_type") or auto_classify(chat_msg["raw_content"])
    logger.info(f"[ROUTING] Classified as: {query_type}")

    agent_payload = {
        "chat_id": chat_msg["id"],
        "query_text": chat_msg["raw_content"],
        "employee_id": chat_msg["sender_id"],
        "query_type": query_type,
        "conversation_history": chat_msg.get("conversation_history", []),
        "context": {
            "sender_role": chat_msg["sender_role"],
            "airport_id": chat_msg["airport_id"]
        }
    }

    # Route to appropriate agent
    if query_type == "general_query":
        result = await query_agent_process(agent_payload)
        result["agent_used"] = "query_agent"

    elif query_type == "leave":
        # Router detects leave intent and delegates to roster agent
        intent = detect_query_intent(chat_msg["raw_content"])
        if intent == "leave_apply":
            # Extract dates via LLM (delegated to Query Agent)
            result = await query_agent_process(agent_payload)
        else:
            # Roster query
            result = await roster_agent_process({
                "event_type": "query",
                "query_text": chat_msg["raw_content"],
                "airport_id": chat_msg["airport_id"],
                "chat_id": chat_msg["id"]
            })
        result["agent_used"] = "roster_agent"

    elif query_type in ["cab", "hotel"]:
        result = await cabhotel_agent_process({
            "chat_id": chat_msg["id"],
            "ticket_type": query_type,
            "requester_id": chat_msg["sender_id"],
            "airport_id": chat_msg["airport_id"],
            "query_text": chat_msg["raw_content"]
        })
        result["agent_used"] = "cabhotel_agent"

    else:
        # Fallback to query agent
        result = await query_agent_process(agent_payload)
        result["agent_used"] = "query_agent"

    return result
