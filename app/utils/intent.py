"""
Intent detection and query classification utilities
"""


def detect_query_intent(text: str) -> str:
    """
    Lightweight keyword classifier for query intent.
    Returns one of: 'leave_balance', 'leave_apply', 'policy_lookup', 'roster_query', 'general'
    """
    t = text.lower()

    # Leave balance queries
    if any(
        w in t
        for w in [
            "how many leave",
            "leave balance",
            "leaves left",
            "leaves remaining",
            "leaves do i have",
            "casual leaves",
            "sick leaves",
            "planned leaves",
        ]
    ):
        return "leave_balance"

    # Leave application
    if any(
        w in t
        for w in [
            "apply leave",
            "take leave",
            "request leave",
            "want leave",
            "need leave from",
            "apply for leave",
            "emergency leave",
        ]
    ):
        return "leave_apply"

    # Policy/SOP queries
    if any(
        w in t
        for w in ["policy", "procedure", "how do i", "how to", "sop", "rule", "guideline"]
    ):
        return "policy_lookup"

    # Roster queries
    if any(
        w in t
        for w in [
            "roster",
            "who is on duty",
            "who is working",
            "standby",
            "duty today",
            "shift",
            "schedule",
        ]
    ):
        return "roster_query"

    return "general"


def auto_classify_cab_hotel(text: str) -> str | None:
    """
    Auto-classify between 'cab' and 'hotel' or None if unclear.
    """
    t = text.lower()
    if any(w in t for w in ["cab", "taxi", "pickup", "drop", "vehicle", "transport"]):
        return "cab"
    if any(w in t for w in ["hotel", "accommodation", "room", "stay", "check-in"]):
        return "hotel"
    return None
