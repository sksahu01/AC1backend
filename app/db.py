"""
Database client singleton using Supabase
Provides async access via supabase-py
"""
from supabase import create_client, Client
from app.config import settings

_db_client: Client | None = None


def get_db() -> Client:
    """Get or create Supabase client singleton"""
    global _db_client
    if _db_client is None:
        _db_client = create_client(settings.supabase_url, settings.supabase_key)
    return _db_client


# Convenience alias
db = get_db()
