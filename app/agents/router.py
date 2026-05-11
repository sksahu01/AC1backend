"""
Router Agent — Flow 1
Routes OpsCards to appropriate task/activity creation.
Called inline by Smart Crawler 2.
"""
import logging
from datetime import datetime, timedelta
from uuid import uuid4
from app.db import db

logger = logging.getLogger("aerocore.router")


async def router_agent_process(ops_card: dict) -> dict:
    """
    Routes an OpsCard to task and activity creation.
    Called inline by Smart Crawler 2.
    
    Args:
        ops_card: Full OpsCard dict from ops_cards table
        
    Returns:
        Dict with task_id and activity_id
    """
    logger.info(f"[ROUTER] Processing OpsCard {ops_card['event_id']}")

    # ─────────────────────────────────────────────────────────
    # STEP 1: SLA CONFIG LOOKUP
    # ─────────────────────────────────────────────────────────
    sla = (
        db.table("sla_configs")
        .select("sla_minutes, escalation_after_minutes")
        .eq("ops_type", ops_card["type"])
        .eq("priority_label", ops_card["priority_label"])
        .execute()
        .data
    )

    sla_mins = sla[0]["sla_minutes"] if sla else 30
    sla_deadline = ops_card.get("deadline_utc") or (
        datetime.utcnow() + timedelta(minutes=sla_mins)
    ).isoformat()

    logger.info(f"[ROUTER] SLA deadline: {sla_deadline} ({sla_mins} min)")

    # ─────────────────────────────────────────────────────────
    # STEP 2: VISIBILITY DETERMINATION
    # ─────────────────────────────────────────────────────────
    def determine_visibility(urgency: int, authority: int) -> list:
        """Determine who can see this task based on urgency and authority."""
        if urgency >= 4 or authority >= 3:
            return [1, 2, 3]  # visible to all
        elif urgency == 3 or authority == 2:
            return [1, 2]  # visible to coordinators and managers
        else:
            return [1]  # visible to coordinators only

    visible = determine_visibility(
        ops_card.get("urgency_score", 3), 
        ops_card.get("authority_level", 1)
    )

    logger.info(f"[ROUTER] Visibility: {visible}")

    # ─────────────────────────────────────────────────────────
    # STEP 3: CREATE KANBAN TASK
    # ─────────────────────────────────────────────────────────
    task_id = f"tsk_{uuid4().hex[:8]}"
    entities = ops_card.get("entities", {})

    # Build labels
    labels = []
    if entities.get("flightNo"):
        labels.append(entities["flightNo"])
    labels.append(ops_card["type"])
    labels.append(ops_card["priority_label"])

    try:
        db.table("tasks").insert({
            "task_id": task_id,
            "airport_id": ops_card["airport_id"],
            "ops_card_id": ops_card.get("event_id"),
            "flight_no": entities.get("flightNo"),
            "title": ops_card["title"],
            "description": ops_card["summary"],
            "status": "New",
            "priority": ops_card.get("priority_score", 70),
            "priority_label": ops_card.get("priority_label", "Medium"),
            "sla_deadline_utc": sla_deadline,
            "visible_to_levels": visible,
            "escalation_level": 0,
            "labels": labels,
            "audit": [
                {
                    "at": datetime.utcnow().isoformat(),
                    "by": "RouterAgent",
                    "action": "created",
                    "note": f"From OpsCard {ops_card['event_id']}"
                }
            ]
        }).execute()

        logger.info(f"[ROUTER] Task created: {task_id}")
    except Exception as e:
        logger.error(f"[ROUTER] Failed to create task: {e}")
        raise

    # ─────────────────────────────────────────────────────────
    # STEP 4: CREATE GANTT ACTIVITY (if time-bound)
    # ─────────────────────────────────────────────────────────
    activity_id = None
    if entities.get("etd") or entities.get("eta"):
        try:
            start = entities.get("etd") or datetime.utcnow().isoformat()
            end = ops_card.get("deadline_utc") or (
                datetime.fromisoformat(start.replace("Z", "+00:00")) + timedelta(minutes=15)
            ).isoformat()

            activity_id = f"act_{uuid4().hex[:8]}"

            db.table("activities").insert({
                "activity_id": activity_id,
                "airport_id": ops_card["airport_id"],
                "flight_no": entities.get("flightNo"),
                "name": ops_card["title"],
                "start_utc": start,
                "end_utc": end,
                "depends_on": [],
                "resource_type": entities.get("resource", "Gate"),
                "resource_id": entities.get("gateTo") or entities.get("standTo"),
                "state": "Planned",
                "source_ops_card_ids": [ops_card["event_id"]],
                "critical_path": ops_card["priority_label"] == "High"
            }).execute()

            logger.info(f"[ROUTER] Activity created: {activity_id}")
        except Exception as e:
            logger.error(f"[ROUTER] Failed to create activity: {e}")

    return {
        "task_id": task_id,
        "activity_id": activity_id,
        "status": "New",
        "priority_label": ops_card.get("priority_label", "Medium"),
        "sla_deadline_utc": sla_deadline,
        "visible_to_levels": visible
    }
