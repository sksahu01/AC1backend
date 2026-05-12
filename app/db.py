"""
Database client singleton using Supabase
Provides async access via supabase-py
Uses lazy initialization to support environment variable loading
"""
from supabase import create_client, Client
from app.config import settings

_db_client: Client | None = None


def get_db() -> Client:
    """Get or create Supabase client singleton (lazy initialization)"""
    global _db_client
    if _db_client is None:
        try:
            _db_client = create_client(settings.supabase_url, settings.supabase_key)
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize Supabase client. "
                f"Check SUPABASE_URL and SUPABASE_KEY environment variables. "
                f"Error: {e}"
            ) from e
    return _db_client


# Lazy alias - only initializes when first accessed
class _DBProxy:
    """Lazy proxy for database client"""
    def __getattr__(self, name):
        return getattr(get_db(), name)


db = _DBProxy()
