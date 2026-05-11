"""
Smart Crawler 1 — MSG DB → Summarizer (inline)
Wakes on NOTIFY 'msg_inbox_insert' or 30s fallback sweep
"""
import asyncio
import logging
from datetime import datetime
from uuid import uuid4
from app.db import db
from app.agents.summarizer import summarizer_process
from app.config import settings

logger = logging.getLogger("aerocore.crawler1")
_lock1 = asyncio.Lock()  # Prevent concurrent runs from same instance


async def smart_crawler_1():
    """
    Main Smart Crawler 1 function.
    Fetches unprocessed messages, calls summarizer inline, commits per-record.
    """
    if _lock1.locked():
        logger.debug("[SC1] Already running — skip this trigger")
        return

    async with _lock1:
        crawler_id = f"sc1_{uuid4().hex[:6]}"

        try:
            # STEP 1: Lock and fetch batch of unprocessed messages
            result = db.rpc(
                "lock_msg_batch",
                {"batch_size": settings.msg_batch_size, "p_crawler_id": crawler_id}
            ).execute()

            records = result.data or []

            if not records:
                logger.debug("[SC1] No unprocessed messages.")
                return

            logger.info(f"[SC1] Processing {len(records)} messages.")

            # STEP 2: Process ONE BY ONE — never batch-commit
            for msg in records:
                try:
                    logger.info(f"[SC1] Processing message {msg['id']}")

                    # Call Summarizer inline — no HTTP hop
                    ops_card = await summarizer_process(msg)

                    if ops_card:
                        # INSERT ops_cards fires NOTIFY → wakes Smart Crawler 2
                        db.table("ops_cards").insert(ops_card).execute()
                        logger.info(f"[SC1] OpsCard created: {ops_card['event_id']}")
                    else:
                        logger.info(f"[SC1] Message {msg['id']} suppressed (duplicate).")

                    # IMMEDIATE per-record commit
                    db.table("msg_inbox").update({
                        "status": "processed",
                        "processed_at": datetime.utcnow().isoformat(),
                        "processing_by": None
                    }).eq("id", msg["id"]).execute()

                    logger.info(f"[SC1] Message {msg['id']} marked processed")

                except Exception as e:
                    logger.error(f"[SC1] Failed on {msg['id']}: {e}", exc_info=True)

                    # Mark failed — does NOT block remaining records
                    db.table("msg_inbox").update({
                        "status": "failed",
                        "error_log": str(e),
                        "retry_count": msg.get("retry_count", 0) + 1,
                        "processing_by": None
                    }).eq("id", msg["id"]).execute()

                    continue  # ← move to next record regardless

        except Exception as e:
            logger.error(f"[SC1] Crawler failure: {e}", exc_info=True)
