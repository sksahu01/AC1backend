"""
Smart Crawler 2 — OPS DB → Router Agent (inline routing)
Wakes on NOTIFY 'ops_cards_insert' or 30s fallback sweep
"""
import asyncio
import logging
from datetime import datetime
from uuid import uuid4
from app.db import db
from app.crawlers.routing import route_ops_card_inline
from app.config import settings

logger = logging.getLogger("aerocore.crawler2")
_lock2 = asyncio.Lock()


async def smart_crawler_2():
    """
    Main Smart Crawler 2 function.
    Fetches unprocessed OpsCards (highest priority first), calls router inline.
    """
    if _lock2.locked():
        logger.debug("[SC2] Already running — skip.")
        return

    async with _lock2:
        crawler_id = f"sc2_{uuid4().hex[:6]}"

        try:
            # STEP 1: Lock batch of unprocessed OpsCards, ordered by priority DESC
            result = db.rpc(
                "lock_ops_batch",
                {"batch_size": settings.ops_batch_size, "p_crawler_id": crawler_id}
            ).execute()

            records = result.data or []

            if not records:
                logger.debug("[SC2] No unprocessed OpsCards.")
                return

            logger.info(f"[SC2] Processing {len(records)} OpsCards.")

            # STEP 2: Process ONE BY ONE
            for card in records:
                try:
                    logger.info(f"[SC2] Processing OpsCard {card['event_id']}")

                    # INLINE ROUTING (replaces /orchestration/route-ops)
                    result = await route_ops_card_inline(card)

                    # Update OpsCard status
                    db.table("ops_cards").update({
                        "status": "processed",
                        "routing_status": "completed",
                        "routed_to": result.get("routed_to", "router_agent"),
                        "processed_at": datetime.utcnow().isoformat(),
                        "processing_by": None
                    }).eq("id", card["id"]).execute()

                    logger.info(f"[SC2] OpsCard {card['event_id']} routed successfully")

                except Exception as e:
                    logger.error(f"[SC2] Failed on {card['id']}: {e}", exc_info=True)

                    # Mark failed — does NOT block remaining cards
                    db.table("ops_cards").update({
                        "status": "failed",
                        "routing_status": "failed",
                        "error_log": str(e),
                        "retry_count": card.get("retry_count", 0) + 1,
                        "processing_by": None
                    }).eq("id", card["id"]).execute()

                    continue

        except Exception as e:
            logger.error(f"[SC2] Crawler failure: {e}", exc_info=True)
