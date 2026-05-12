"""
asyncpg LISTEN setup for PostgreSQL NOTIFY channels
Opens dedicated connections per channel and registers callbacks.
"""
import asyncpg
import asyncio
import logging
from app.config import settings

logger = logging.getLogger("aerocore.listener")


async def start_listeners(smart_crawler_1, smart_crawler_2, smart_crawler_3):
    """
    Open asyncpg connections and set up LISTEN callbacks for all three channels.
    Called once during FastAPI lifespan startup.
    
    Args:
        smart_crawler_1: async function for msg_inbox crawler
        smart_crawler_2: async function for ops_cards crawler
        smart_crawler_3: async function for chat_inbox crawler
        
    Returns:
        Tuple of connections (conn_msg, conn_ops, conn_chat) for cleanup on shutdown
    """
    logger.info("[LISTENER] Starting NOTIFY listeners...")

    try:
        conn_msg = await asyncpg.connect(
    settings.supabase_db_url,
    statement_cache_size=0
)
        conn_ops = await asyncpg.connect(
    settings.supabase_db_url,
    statement_cache_size=0
)
        conn_chat = await asyncpg.connect(
    settings.supabase_db_url,
    statement_cache_size=0
)
    except Exception as e:
        logger.error(f"[LISTENER] Failed to connect to database: {e}")
        raise

    # ── Listener 1: msg_inbox → Smart Crawler 1
    async def on_msg_insert(conn, pid, channel, payload):
        logger.debug(f"[L1] msg_inbox NOTIFY received: {payload}")
        await asyncio.sleep(0.3)  # brief debounce to batch rapid inserts
        await smart_crawler_1()

    try:
        await conn_msg.add_listener("msg_inbox_insert", on_msg_insert)
        logger.info("[L1] Listening on msg_inbox_insert")
    except Exception as e:
        logger.error(f"[L1] Failed to add listener: {e}")
        await conn_msg.close()
        raise

    # ── Listener 2: ops_cards → Smart Crawler 2
    async def on_ops_insert(conn, pid, channel, payload):
        logger.debug(f"[L2] ops_cards NOTIFY received: {payload}")
        await asyncio.sleep(0.3)
        await smart_crawler_2()

    try:
        await conn_ops.add_listener("ops_cards_insert", on_ops_insert)
        logger.info("[L2] Listening on ops_cards_insert")
    except Exception as e:
        logger.error(f"[L2] Failed to add listener: {e}")
        await conn_ops.close()
        raise

    # ── Listener 3: chat_inbox → Smart Crawler 3
    async def on_chat_insert(conn, pid, channel, payload):
        logger.debug(f"[L3] chat_inbox NOTIFY received: {payload}")
        await asyncio.sleep(0.3)
        await smart_crawler_3()

    try:
        await conn_chat.add_listener("chat_inbox_insert", on_chat_insert)
        logger.info("[L3] Listening on chat_inbox_insert")
    except Exception as e:
        logger.error(f"[L3] Failed to add listener: {e}")
        await conn_chat.close()
        raise

    logger.info("[LISTENER] All LISTEN channels active.")
    return conn_msg, conn_ops, conn_chat
