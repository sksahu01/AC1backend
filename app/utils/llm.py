"""
LLM integration utilities
Uses Anthropic API via the SDK
"""
import json
import logging
from anthropic import Anthropic
from app.config import settings

logger = logging.getLogger("aerocore.llm")

# Global client
_client: Anthropic | None = None


def get_llm_client() -> Anthropic:
    """Get or create Anthropic client"""
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.llm_api_key)
    return _client


async def call_llm(system: str, user: str) -> str:
    """
    Call Claude via Anthropic API.
    Returns text response.
    """
    try:
        client = get_llm_client()
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=2048,
            system=system,
            messages=[
                {"role": "user", "content": user}
            ]
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise


async def call_llm_json(system: str, user: str) -> dict:
    """
    Call Claude and parse response as JSON.
    """
    text = await call_llm(system, user)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        logger.error(f"Raw response: {text}")
        raise
