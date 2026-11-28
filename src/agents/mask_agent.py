"""Local PII masker entrypoint for the Masker A2A server (no cloud SDK or LLM)."""

from __future__ import annotations

from src.security.masker import mask_sensitive_data


def mask_text(text: str) -> dict:
    """Mask sensitive spans with the local masker."""
    return {"masked_text": mask_sensitive_data(text)}


async def call_mask_agent(text: str) -> str:
    """Redact ``text`` with the local masker. Does not call a cloud SDK."""
    return mask_sensitive_data(text)
