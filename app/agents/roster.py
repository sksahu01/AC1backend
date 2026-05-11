"""
Roster Agent — Flow 2
Handles leave requests, backup recommendations, and roster queries.
Called inline by Smart Crawler 3 OR by Query Agent.
"""
import json
import logging
from datetime import datetime, date
from uuid import uuid4
from app.db import db
from app.utils.llm import call_llm

logger = logging.getLogger("aerocore.roster")


async def roster_agent_process(payload: dict) -> dict:
    """
    Roster Agent main function. Handles leave_request and query events.
    Called inline by Smart Crawler 3 or delegated from Query Agent.
    
    Args:
        payload: Dict with event_type, employee_id, leave details, or query_text
        
    Returns:
        Dict with response, recommendations, data, etc.
    """
    event_type = payload.get("event_type", "leave_request")

    logger.info(f"[ROSTER] Processing event: {event_type}")

    # ─────────────────────────────────────────────────────────
    # EVENT: leave_request
    # ─────────────────────────────────────────────────────────
    if event_type == "leave_request":
        return await handle_leave_request(payload)

    # ─────────────────────────────────────────────────────────
    # EVENT: query
    # ─────────────────────────────────────────────────────────
    if event_type == "query":
        return await handle_roster_query(payload)

    # Default
    return {
        "response": "Unknown roster event type.",
        "source": "roster_agent",
        "action_taken": False
    }


async def handle_leave_request(payload: dict) -> dict:
    """Handle leave request event"""
    emp_id = payload.get("employee_id")
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    leave_type = payload.get("leave_type", "casual")
    reason = payload.get("reason", "")
    chat_id = payload.get("chat_id")

    if not emp_id or not start_date or not end_date:
        return {
            "response": "Missing required leave details (employee_id, start_date, end_date).",
            "source": "roster_agent",
            "action_taken": False
        }

    logger.info(f"[ROSTER] Leave request: {emp_id} from {start_date} to {end_date}")

    try:
        # Query affected duty slots
        affected = (
            db.table("roster")
            .select("*")
            .eq("employee_id", str(emp_id))
            .gte("duty_date", str(start_date))
            .lte("duty_date", str(end_date))
            .in_("status", ["Scheduled"])
            .execute()
            .data
        )

        logger.info(f"[ROSTER] Affected slots: {len(affected)}")

        # Get employee designation
        emp = (
            db.table("users")
            .select("designation, airport_id")
            .eq("id", str(emp_id))
            .single()
            .execute()
            .data
        )

        if not emp:
            return {
                "response": "Employee not found.",
                "source": "roster_agent",
                "action_taken": False
            }

        designation = emp.get("designation", "")
        airport_id = emp.get("airport_id", "")

        # Find backup candidates for each affected slot
        recommendations = []
        for slot in affected:
            backups = (
                db.table("roster")
                .select("employee_id, rest_hours_before, shift_start_utc")
                .eq("duty_date", str(slot["duty_date"]))
                .in_("status", ["Standby", "Scheduled"])
                .eq("is_backup", True)
                .eq("airport_id", airport_id)
                .gte("rest_hours_before", 8)
                .neq("employee_id", str(emp_id))
                .order("rest_hours_before", desc=True)
                .limit(3)
                .execute()
                .data
            )

            for i, b in enumerate(backups):
                u = (
                    db.table("users")
                    .select("name, designation")
                    .eq("id", str(b["employee_id"]))
                    .single()
                    .execute()
                    .data
                )

                if u and u.get("designation") == designation:
                    recommendations.append({
                        "rank": i + 1,
                        "employee_id": str(b["employee_id"]),
                        "name": u.get("name", "Unknown"),
                        "designation": u.get("designation", ""),
                        "rest_hours_available": b.get("rest_hours_before", 0),
                        "duty_date": str(slot["duty_date"]),
                        "compliance": "OK",
                        "reason": f"Rank {i+1} by available rest hours"
                    })

        # Insert leave request
        lr = (
            db.table("leave_requests")
            .insert({
                "employee_id": str(emp_id),
                "leave_type": leave_type,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "reason": reason,
                "status": "Pending",
                "source_chat_id": str(chat_id) if chat_id else None
            })
            .execute()
            .data[0]
        )

        logger.info(f"[ROSTER] Leave request created: {lr.get('id')}")

        return {
            "response": (
                f"Leave request submitted for {start_date} to {end_date}. "
                f"Your manager has been notified with backup recommendations."
            ),
            "leave_request_id": str(lr.get("id")),
            "affected_duty_slots": len(affected),
            "backup_recommendations": recommendations,
            "manager_action_required": True,
            "source": "roster_agent",
            "action_taken": True
        }

    except Exception as e:
        logger.error(f"[ROSTER] Leave request failed: {e}")
        return {
            "response": f"Error processing leave request: {str(e)}",
            "source": "roster_agent",
            "action_taken": False
        }


async def handle_roster_query(payload: dict) -> dict:
    """Handle roster query event"""
    query_text = payload.get("query_text", "")
    airport_id = payload.get("airport_id", "")

    if not airport_id:
        return {
            "response": "Airport ID required for roster query.",
            "source": "roster_agent",
            "action_taken": False
        }

    logger.info(f"[ROSTER] Query: {query_text}")

    try:
        # Get duty roster for today
        today = date.today().isoformat()
        duty_rows = (
            db.table("roster")
            .select("employee_id, designation, shift_start_utc, shift_end_utc, flight_no")
            .eq("duty_date", today)
            .eq("airport_id", airport_id)
            .in_("status", ["Scheduled", "OnDuty"])
            .execute()
            .data
        )

        # Enrich with user names
        enriched = []
        for row in duty_rows:
            u = (
                db.table("users")
                .select("name")
                .eq("id", str(row["employee_id"]))
                .single()
                .execute()
                .data
            )
            enriched.append({
                **row,
                "name": u.get("name", "Unknown") if u else "Unknown"
            })

        # Use LLM to answer query based on roster data
        llm_prompt = f"""
Answer this roster question based on the provided roster data.
Question: {query_text}

Today's Roster:
{json.dumps(enriched, indent=2, default=str)}

Be concise and professional.
"""

        answer = await call_llm(
            "Answer roster questions based only on the provided data.",
            llm_prompt
        )

        return {
            "response": answer,
            "source": "roster_agent",
            "action_taken": False,
            "data": enriched
        }

    except Exception as e:
        logger.error(f"[ROSTER] Query failed: {e}")
        return {
            "response": f"Error querying roster: {str(e)}",
            "source": "roster_agent",
            "action_taken": False
        }


async def confirm_roster_assignment(payload: dict, user_id: str) -> dict:
    """
    Manager confirms a backup assignment for a leave request.
    Updates leave_requests and roster entries.
    
    Args:
        payload: Dict with leave_request_id, backup_employee_id
        user_id: Manager's user ID
    """
    lr_id = payload.get("leave_request_id")
    backup_id = payload.get("backup_employee_id")

    logger.info(f"[ROSTER] Confirming assignment: LR={lr_id}, Backup={backup_id}")

    try:
        # Get leave request
        lr = (
            db.table("leave_requests")
            .select("*")
            .eq("id", str(lr_id))
            .single()
            .execute()
            .data
        )

        if not lr:
            return {"error": "Leave request not found"}

        # Update leave request
        db.table("leave_requests").update({
            "status": "Approved",
            "backup_assigned_to": str(backup_id),
            "approved_by": str(user_id)
        }).eq("id", str(lr_id)).execute()

        # Mark original employee slots as Leave
        db.table("roster").update({
            "status": "Leave"
        }).eq("employee_id", str(lr["employee_id"])).gte(
            "duty_date", str(lr["start_date"])
        ).lte("duty_date", str(lr["end_date"])).execute()

        logger.info(f"[ROSTER] Assignment confirmed")
        return {"message": "Roster updated and backup assigned", "approved": True}

    except Exception as e:
        logger.error(f"[ROSTER] Confirm assignment failed: {e}")
        return {"error": str(e)}
