"""
Query Agent — Flow 2
Handles general queries, leave balance, policy lookups, and roster queries.
Called inline by Smart Crawler 3 OR directly via POST /agents/query/process
"""
import json
import logging
from datetime import datetime
from app.db import db
from app.utils.intent import detect_query_intent
from app.utils.llm import call_llm, call_llm_json

logger = logging.getLogger("aerocore.query")

QUERY_AGENT_SYSTEM_PROMPT = """
You are a helpful HR and operational assistant for an airport operations team.
Answer queries based on provided documents and database information.
Be concise and professional.
If you don't have the information, say so clearly.
"""


async def query_agent_process(payload: dict) -> dict:
    """
    Main Query Agent function. Called inline by Smart Crawler 3.
    Handles multiple intent types: leave_balance, leave_apply, policy_lookup, roster_query, general
    
    Args:
        payload: Dict with query_text, employee_id, query_type, conversation_history, context
        
    Returns:
        Dict with response, source, data, etc.
    """
    query_text = payload.get("query_text", "")
    employee_id = payload.get("employee_id")
    query_type = payload.get("query_type", "general_query")

    logger.info(f"[QUERY] Processing {query_type}: {query_text[:60]}")

    # Auto-detect intent if not specified
    if query_type == "general_query":
        intent = detect_query_intent(query_text)
    else:
        intent = query_type

    # ─────────────────────────────────────────────────────────
    # leave_balance — Query leave_balances table
    # ─────────────────────────────────────────────────────────
    if intent == "leave_balance":
        try:
            lb = (
                db.table("leave_balances")
                .select("*")
                .eq("employee_id", str(employee_id))
                .single()
                .execute()
                .data
            )

            if not lb:
                return {
                    "response": "Leave balance not found in system.",
                    "intent_detected": "leave_balance",
                    "source": "hr_database",
                    "action_taken": False,
                    "data": {}
                }

            casual_remaining = lb.get("casual_total", 12) - lb.get("casual_used", 0)
            sick_remaining = lb.get("sick_total", 10) - lb.get("sick_used", 0)
            planned_remaining = lb.get("planned_total", 15) - lb.get("planned_used", 0)

            response = (
                f"You have {casual_remaining} casual leaves remaining, "
                f"{sick_remaining} sick leaves, and {planned_remaining} planned leaves "
                f"for FY {lb.get('financial_year', 'N/A')}."
            )

            return {
                "response": response,
                "intent_detected": "leave_balance",
                "source": "hr_database",
                "action_taken": False,
                "data": {
                    "casual": {"total": lb.get("casual_total"), "used": lb.get("casual_used")},
                    "sick": {"total": lb.get("sick_total"), "used": lb.get("sick_used")},
                    "planned": {"total": lb.get("planned_total"), "used": lb.get("planned_used")}
                }
            }
        except Exception as e:
            logger.error(f"[QUERY] Failed to fetch leave balance: {e}")
            return {
                "response": f"Error fetching leave balance: {str(e)}",
                "intent_detected": "leave_balance",
                "source": "error",
                "action_taken": False
            }

    # ─────────────────────────────────────────────────────────
    # leave_apply — delegate to Roster Agent
    # ─────────────────────────────────────────────────────────
    if intent == "leave_apply":
        from app.agents.roster import roster_agent_process

        # Extract dates from query using LLM
        try:
            extraction_prompt = f"""
Extract leave parameters from this request: "{query_text}"
Return JSON with: start_date (YYYY-MM-DD), end_date (YYYY-MM-DD), leave_type (casual|sick|emergency|planned), reason (optional string)
"""
            params = await call_llm_json(
                "Extract only the JSON, no explanation.",
                extraction_prompt
            )
        except Exception as e:
            logger.error(f"[QUERY] LLM extraction failed: {e}")
            params = {
                "start_date": None,
                "end_date": None,
                "leave_type": "casual",
                "reason": query_text
            }

        return await roster_agent_process({
            "event_type": "leave_request",
            "employee_id": employee_id,
            "chat_id": payload.get("chat_id"),
            **params
        })

    # ─────────────────────────────────────────────────────────
    # policy_lookup — RAG over hr_documents
    # ─────────────────────────────────────────────────────────
    if intent == "policy_lookup":
        try:
            docs = (
                db.table("hr_documents")
                .select("title, content, doc_type")
                .eq("is_active", True)
                .execute()
                .data
            )

            # Simple keyword matching (in prod, use pgvector embeddings)
            query_words = set(query_text.lower().split())
            scored_docs = []
            for doc in docs:
                content_words = set(doc["content"].lower().split())
                matches = len(query_words & content_words)
                if matches > 0:
                    scored_docs.append((matches, doc))

            scored_docs.sort(reverse=True)
            top_docs = [d[1] for d in scored_docs[:3]]

            if not top_docs:
                return {
                    "response": "No policy documents found matching your query.",
                    "intent_detected": "policy_lookup",
                    "source": "rag_model",
                    "action_taken": False,
                    "sources": []
                }

            context_text = "\n---\n".join([d["content"][:500] for d in top_docs])
            answer = await call_llm(
                "Answer based only on the provided documents. Be concise.",
                f"Question: {query_text}\n\nDocuments:\n{context_text}"
            )

            return {
                "response": answer,
                "intent_detected": "policy_lookup",
                "source": "rag_model",
                "action_taken": False,
                "sources": [d["title"] for d in top_docs]
            }
        except Exception as e:
            logger.error(f"[QUERY] Policy lookup failed: {e}")
            return {
                "response": f"Error looking up policy: {str(e)}",
                "intent_detected": "policy_lookup",
                "source": "error",
                "action_taken": False
            }

    # ─────────────────────────────────────────────────────────
    # roster_query — delegate to Roster Agent
    # ─────────────────────────────────────────────────────────
    if intent == "roster_query":
        from app.agents.roster import roster_agent_process

        return await roster_agent_process({
            "event_type": "query",
            "query_text": query_text,
            "airport_id": payload.get("context", {}).get("airport_id"),
            "chat_id": payload.get("chat_id")
        })

    # ─────────────────────────────────────────────────────────
    # general — RAG + LLM
    # ─────────────────────────────────────────────────────────
    try:
        docs = (
            db.table("hr_documents")
            .select("content")
            .eq("is_active", True)
            .limit(2)
            .execute()
            .data
        )

        ctx = "\n".join([d["content"][:400] for d in docs]) if docs else ""
        answer = await call_llm(
            QUERY_AGENT_SYSTEM_PROMPT,
            f"Question: {query_text}\n\nContext: {ctx}" if ctx else f"Question: {query_text}"
        )

        return {
            "response": answer,
            "intent_detected": "general",
            "source": "llm_rag",
            "action_taken": False,
            "data": {}
        }
    except Exception as e:
        logger.error(f"[QUERY] General query failed: {e}")
        return {
            "response": f"Error processing query: {str(e)}",
            "intent_detected": "general",
            "source": "error",
            "action_taken": False
        }
