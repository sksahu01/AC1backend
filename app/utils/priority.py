"""
Priority scoring and timing utilities for OpsCard prioritization
"""
from datetime import datetime, timedelta


def compute_time_left(deadline_utc: str | datetime | None, received_at: str | datetime) -> float:
    """
    Compute minutes remaining until deadline.
    If deadline is None, return 120 (default).
    """
    if deadline_utc is None:
        return 120.0

    if isinstance(deadline_utc, str):
        deadline = datetime.fromisoformat(deadline_utc.replace("Z", "+00:00"))
    else:
        deadline = deadline_utc

    if isinstance(received_at, str):
        received = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    else:
        received = received_at

    time_delta = deadline - received
    return time_delta.total_seconds() / 60


def compute_priority(
    time_left_min: float,
    urgency_score: int,
    authority_level: int,
    impact: int,
    confidence: float,
    is_redundant: bool = False
) -> float:
    """
    Compute priority score (0-100+).
    
    Formula:
    - base: 50
    - time_factor: (120 - time_left_min) / 120 * 30
    - urgency_factor: urgency_score * 4
    - auth_factor: authority_level * 3
    - impact_factor: impact * 5
    - conf_adj: (confidence - 0.7) * 20
    - redundancy_pen: -40 if redundant else 0
    """
    base = 50
    time_factor = max(0.0, min(1.0, (120 - time_left_min) / 120)) * 30
    urgency_factor = urgency_score * 4
    auth_factor = authority_level * 3
    impact_factor = impact * 5
    conf_adj = (confidence - 0.7) * 20
    redundancy_pen = -40 if is_redundant else 0

    score = (
        base
        + time_factor
        + urgency_factor
        + auth_factor
        + impact_factor
        + conf_adj
        + redundancy_pen
    )

    return round(score, 2)


def get_priority_label(score: float) -> str:
    """
    Convert priority score to label.
    High >= 85, Medium >= 70, Low < 70
    """
    if score >= 85:
        return "High"
    elif score >= 70:
        return "Medium"
    else:
        return "Low"
