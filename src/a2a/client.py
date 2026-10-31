"""JSON-RPC client for a remote Judge or Masker A2A server."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


def _payload(method: str, query: str, task_id: str, session_id: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": {
            "id": task_id,
            "sessionId": session_id,
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": query}],
            },
        },
    }


def _text_from_parts(parts: list[dict[str, Any]]) -> str:
    for part in parts:
        if part.get("type") == "text":
            return str(part.get("text", ""))
    return ""


def _text_from_task(task: dict[str, Any]) -> str:
    artifacts = task.get("artifacts") or []
    if artifacts:
        text = _text_from_parts(artifacts[0].get("parts") or [])
        if text:
            return text
    message = (task.get("status") or {}).get("message") or {}
    return _text_from_parts(message.get("parts") or [])


async def call_a2a_agent(query: str, host: str, port: int, stream: bool = False) -> str:
    """Send ``query`` to an A2A server and return the agent's text."""
    url = f"http://{host}:{port}/rpc"
    task_id = f"task-{uuid.uuid4()}"
    session_id = f"session-{uuid.uuid4()}"
    if stream:
        return await _call_stream(query, url, task_id, session_id)
    return await _call_sync(query, url, task_id, session_id)


async def _call_sync(query: str, url: str, task_id: str, session_id: str) -> str:
    payload = _payload("tasks/send", query, task_id, session_id)
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error("Error calling agent: %s", error_text)
                raise RuntimeError(f"Error calling agent: {error_text}")
            result = await response.json()
    if "error" in result:
        logger.error("Agent returned error: %s", result["error"])
        raise RuntimeError(f"Agent error: {result['error']['message']}")
    return _text_from_task(result.get("result") or {})


async def _call_stream(query: str, url: str, task_id: str, session_id: str) -> str:
    payload = _payload("tasks/sendSubscribe", query, task_id, session_id)
    result_text = ""
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error("Error calling agent: %s", error_text)
                raise RuntimeError(f"Error calling agent: {error_text}")
            async for raw in response.content:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data = json.loads(line[6:])
                artifact = (data.get("result") or {}).get("artifact")
                if not artifact:
                    continue
                text = _text_from_parts(artifact.get("parts") or [])
                if text:
                    result_text = text
    return result_text
