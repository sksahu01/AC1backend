"""
Hashing utilities for deduplication
"""
import hashlib


def compute_dedup_hash(flight_no: str | None, message_type: str, airport_id: str, day: str) -> str:
    """
    Compute SHA256 hash for deduplication.
    Used to prevent duplicate OpsCards within a 2-hour window on the same day.
    
    Args:
        flight_no: Flight number (or empty string)
        message_type: Type of message (task, info, alert, etc.)
        airport_id: Airport identifier
        day: Date in YYYY-MM-DD format
    """
    hash_input = f"{flight_no or ''}:{message_type}:{airport_id}:{day}"
    return hashlib.sha256(hash_input.encode()).hexdigest()
