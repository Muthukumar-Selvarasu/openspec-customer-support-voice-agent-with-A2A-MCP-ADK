"""Mem0 search and save tools scoped to the authenticated shopper."""

from __future__ import annotations

import os
from typing import Any

_client = None


def _get_client():
    """Build the Mem0 client on first use so import does not need ``MEM0_API_KEY``."""
    global _client
    if _client is None:
        from mem0 import MemoryClient

        _client = MemoryClient(api_key=os.getenv("MEM0_API_KEY"))
    return _client


def search_memory(query: str, user_id: str) -> dict[str, Any]:
    """Search memories for ``user_id`` only. The caller supplies the session identity."""
    filters = {"user_id": user_id}
    memories = _get_client().search(query, filters=filters)
    results = memories.get("results") or []
    if not results:
        return {"status": "no_memories", "message": "No relevant memories found"}
    memory_context = "\n".join(f"- {item['memory']}" for item in results)
    return {"status": "success", "memories": memory_context}


def save_memory(messages: Any, user_id: str) -> dict[str, Any]:
    """Persist ``messages`` under the authenticated ``user_id``."""
    try:
        result = _get_client().add(messages, user_id=user_id)
        return {
            "status": "success",
            "message": "Information saved to memory",
            "result": result,
        }
    except Exception as exc:
        return {"status": "error", "message": f"Failed to save memory: {exc}"}
