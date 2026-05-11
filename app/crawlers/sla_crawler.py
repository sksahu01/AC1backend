"""
SLA Crawler — Escalation Engine
Interval-based (not insert-driven). Runs every 60 seconds.
Monitors task SLA deadlines and escalates breaches.
"""
import logging
from datetime import datetime, timedelta
from uuid import uuid4
from app.db import db
from app.config import settings

logger = logging.getLogger("aerocore.sla_crawler")


async def crawl_sla_breaches():
    """
    SLA Crawler main function. Runs on 60s interval via APScheduler.
    Detects breached tasks, escalates visibility, and creates escalation OpsCards.
    """
    now = datetime.utcnow()
    now_iso = now.isoformat()

    logger.debug("[SLA] Starting SLA breach scan")

    try:
        # Query for breached tasks: past deadline AND not done
        breached = (
            db.table("tasks")
            .select("*")
            .not_.in_("status", ["Done"])
            .lt("sla_deadline_utc", now_iso)
            .execute()
            .data
        )

        if not breached:
            logger.debug("[SLA] No breached tasks")
            return

        logger.info(f"[SLA] Found {len(breached)} breached tasks")

        # ─────────────────────────────────────────────────────────
        # STEP 1: Escalate each breached task
        # ─────────────────────────────────────────────────────────
        for task in breached:
            try:
                overdue_min = (
                    now - 
                    datetime.fromisoformat(
                        task["sla_deadline_utc"].replace("Z", "+00:00")
                    )
                ).total_seconds() / 60

                new_level = task["escalation_level"] + 1
                next_auth_lvl = min(task["escalation_level"] + 2, 5)
                new_visible = sorted(
                    list(set(task.get("visible_to_levels", [1, 2, 3]) + [next_auth_lvl]))
                )

                # Update task
                db.table("tasks").update({
                    "escalation_level": new_level,
                    "visible_to_levels": new_visible,
                    "updated_at": now_iso,
                    "audit": (task.get("audit", []) or []) + [
                        {
                            "at": now_iso,
                            "by": "SLACrawler",
                            "action": f"escalated_to_L{next_auth_lvl}",
                            "overdue_min": round(overdue_min, 1)
                        }
                    ]
                }).eq("task_id", task["task_id"]).execute()

                logger.info(
                    f"[SLA] Task {task['task_id']} escalated: L{new_level}, "
                    f"visible to {new_visible} (overdue {overdue_min:.0f}min)"
                )

            except Exception as e:
                logger.error(f"[SLA] Failed to escalate {task['id']}: {e}")
                continue

        # ─────────────────────────────────────────────────────────
        # STEP 2: Create escalation OpsCards for level >= 2
        # ─────────────────────────────────────────────────────────
        for task in [t for t in breached if t.get("escalation_level", 0) >= 1]:
            try:
                # Check if escalation OpsCard already exists for this task
                existing = (
                    db.table("ops_cards")
                    .select("id")
                    .eq("type", "escalation")
                    .execute()
                    .data
                )

                # Simple check: avoid duplicates with same parent task
                parent_exists = any(
                    task["task_id"] in str(oc.get("lineage", {}))
                    for oc in existing
                )

                if parent_exists:
                    logger.debug(f"[SLA] Escalation OpsCard already exists for {task['task_id']}")
                    continue

                # Compute overdue
                overdue_min = (
                    now - 
                    datetime.fromisoformat(
                        task["sla_deadline_utc"].replace("Z", "+00:00")
                    )
                ).total_seconds() / 60

                # Create escalation OpsCard
                ts = now.strftime("%Y%m%d_%H%M%S")
                esc_event_id = f"esc_{uuid4().hex[:8]}"

                db.table("ops_cards").insert({
                    "event_id": esc_event_id,
                    "airport_id": task.get("airport_id"),
                    "type": "escalation",
                    "title": f"ESCALATION: {task['title']}",
                    "summary": (
                        f"Task overdue by {round(overdue_min, 0):.0f} minutes. "
                        f"No action taken. Escalating to management."
                    ),
                    "actions_required": [
                        "Review blocked task",
                        "Take corrective action or reassign",
                        "Notify management"
                    ],
                    "entities": task.get("entities", {}),
                    "priority_score": 99.0,
                    "priority_label": "High",
                    "urgency_score": 5,
                    "impact": 5,
                    "confidence": 0.95,
                    "authority_level": min(task.get("escalation_level", 0) + 2, 5),
                    "lineage": {
                        "parent_task_id": task["task_id"],
                        "parent_ops_card": task.get("ops_card_id"),
                        "by": "SLACrawler",
                        "createdAt": now_iso,
                        "overdue_min": round(overdue_min, 1)
                    },
                    "status": "unprocessed"
                }).execute()

                logger.info(f"[SLA] Escalation OpsCard created: {esc_event_id}")

            except Exception as e:
                logger.error(f"[SLA] Failed to create escalation OpsCard: {e}")
                continue

    except Exception as e:
        logger.error(f"[SLA] Crawler failure: {e}", exc_info=True)
