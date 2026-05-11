"""
Smart Crawler 3 — Chat DB → Agents (inline routing)
Wakes on NOTIFY 'chat_inbox_insert' or 30s fallback sweep
"""
import asyncio
import logging
from datetime import datetime
from uuid import uuid4
from app.db import db
from app.crawlers.routing import route_chat_inline
from app.config import settings

logger = logging.getLogger("aerocore.crawler3")
_lock3 = asyncio.Lock()


async def smart_crawler_3():
    """
    Main Smart Crawler 3 function.
    Fetches unprocessed chat messages, calls inline routing to appropriate agent.
    """
    if _lock3.locked():
        logger.debug("[SC3] Already running — skip.")
        return

    async with _lock3:
        crawler_id = f"sc3_{uuid4().hex[:6]}"

        try:
            # STEP 1: Lock batch of unprocessed chat messages
            result = db.rpc(
                "lock_chat_batch",
                {"batch_size": settings.chat_batch_size, "p_crawler_id": crawler_id}
            ).execute()

            records = result.data or []

            if not records:
                logger.debug("[SC3] No unprocessed chat messages.")
                return

            logger.info(f"[SC3] Processing {len(records)} chat messages.")

            # STEP 2: Process ONE BY ONE
            for msg in records:
                try:
                    logger.info(f"[SC3] Processing chat {msg['id']}")

                    # INLINE ROUTING (replaces /orchestration/route-chat)
                    result = await route_chat_inline(msg)

                    # Write response back to the chat_inbox row
                    db.table("chat_inbox").update({
                        "status": "processed",
                        "processed_at": datetime.utcnow().isoformat(),
                        "processing_by": None,
                        "response": result.get("response", ""),
                        "response_source": result.get("agent_used", ""),
                        "response_data": result.get("data", {})
                    }).eq("id", msg["id"]).execute()

                    logger.info(f"[SC3] Chat {msg['id']} processed by {result.get('agent_used')}")

                except Exception as e:
                    logger.error(f"[SC3] Failed on {msg['id']}: {e}", exc_info=True)

                    # Mark failed — does NOT block remaining messages
                    db.table("chat_inbox").update({
                        "status": "failed",
                        "error_log": str(e),
                        "retry_count": msg.get("retry_count", 0) + 1,
                        "processing_by": None
                    }).eq("id", msg["id"]).execute()

                    continue

        except Exception as e:
            logger.error(f"[SC3] Crawler failure: {e}", exc_info=True)
