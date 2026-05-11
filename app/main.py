"""
FastAPI Main Application
Includes lifespan setup for NOTIFY listeners and scheduler.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Import routers
from app.routes import auth, ingress

# Import crawlers
from app.crawlers.listener import start_listeners
from app.crawlers.msg_crawler import smart_crawler_1
from app.crawlers.ops_crawler import smart_crawler_2
from app.crawlers.chat_crawler import smart_crawler_3
from app.crawlers.sla_crawler import crawl_sla_breaches

from app.config import settings

logger = logging.getLogger("aerocore")

# Global scheduler and listener connections
scheduler: AsyncIOScheduler | None = None
_listener_conns: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Startup: Start NOTIFY listeners and scheduler.
    Shutdown: Clean up connections and scheduler.
    """
    global scheduler, _listener_conns

    logger.info("═" * 80)
    logger.info("AEROCORE v4 — Starting Backend")
    logger.info("═" * 80)

    # ── START: NOTIFY Listeners (primary trigger) ─────────────
    try:
        logger.info("[LIFESPAN] Starting NOTIFY listeners...")
        conns = await start_listeners(
            smart_crawler_1,
            smart_crawler_2,
            smart_crawler_3
        )
        _listener_conns.extend(conns)
        logger.info("[LIFESPAN] NOTIFY listeners active")
    except Exception as e:
        logger.error(f"[LIFESPAN] Failed to start listeners: {e}")
        raise

    # ── START: Scheduler (fallback sweeps + SLA crawler) ─────────
    try:
        logger.info("[LIFESPAN] Starting APScheduler...")
        scheduler = AsyncIOScheduler(timezone="UTC")

        # Fallback sweeps (resilience — catches any missed NOTIFYs)
        scheduler.add_job(
            smart_crawler_1,
            "interval",
            seconds=settings.crawler_fallback_sweep_sec,
            id="sc1_fallback",
            max_instances=1,
            coalesce=True
        )
        logger.info(f"[LIFESPAN] SC1 fallback sweep: every {settings.crawler_fallback_sweep_sec}s")

        scheduler.add_job(
            smart_crawler_2,
            "interval",
            seconds=settings.crawler_fallback_sweep_sec,
            id="sc2_fallback",
            max_instances=1,
            coalesce=True
        )
        logger.info(f"[LIFESPAN] SC2 fallback sweep: every {settings.crawler_fallback_sweep_sec}s")

        scheduler.add_job(
            smart_crawler_3,
            "interval",
            seconds=settings.crawler_fallback_sweep_sec,
            id="sc3_fallback",
            max_instances=1,
            coalesce=True
        )
        logger.info(f"[LIFESPAN] SC3 fallback sweep: every {settings.crawler_fallback_sweep_sec}s")

        # SLA Crawler (time-driven, not insert-driven)
        scheduler.add_job(
            crawl_sla_breaches,
            "interval",
            seconds=settings.sla_crawler_interval_sec,
            id="sla_crawler",
            max_instances=1,
            coalesce=True
        )
        logger.info(f"[LIFESPAN] SLA crawler: every {settings.sla_crawler_interval_sec}s")

        scheduler.start()
        logger.info("[LIFESPAN] APScheduler running")

    except Exception as e:
        logger.error(f"[LIFESPAN] Failed to start scheduler: {e}")
        raise

    logger.info("═" * 80)
    logger.info("AEROCORE Ready")
    logger.info("═" * 80)

    yield  # ← Application runs here

    # ── SHUTDOWN: Stop scheduler ─────────────────────────────
    try:
        logger.info("[LIFESPAN] Shutting down APScheduler...")
        if scheduler and scheduler.running:
            scheduler.shutdown(wait=True)
        logger.info("[LIFESPAN] APScheduler stopped")
    except Exception as e:
        logger.error(f"[LIFESPAN] Error stopping scheduler: {e}")

    # ── SHUTDOWN: Close listener connections ─────────────────
    try:
        logger.info("[LIFESPAN] Closing NOTIFY connections...")
        for conn in _listener_conns:
            await conn.close()
        logger.info("[LIFESPAN] Connections closed")
    except Exception as e:
        logger.error(f"[LIFESPAN] Error closing connections: {e}")

    logger.info("═" * 80)
    logger.info("AEROCORE Backend stopped")
    logger.info("═" * 80)


# Create FastAPI app
app = FastAPI(
    title="AEROCORE v4 — Agentic AI Operations Platform",
    description="POC Edition. Python FastAPI + Supabase PostgreSQL + asyncpg",
    version="4.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Include routers
app.include_router(auth.router)
app.include_router(ingress.router)

# Health check endpoint
@app.get("/health")
async def health():
    """Simple health check"""
    return {"status": "ok", "version": "4.0.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info"
    )
