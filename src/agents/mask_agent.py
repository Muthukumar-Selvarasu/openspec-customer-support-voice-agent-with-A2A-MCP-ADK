"""Masker agent. Redaction is the local Group 3 masker, not a cloud API."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools.function_tool import FunctionTool

from src.security.masker import mask_sensitive_data

MASK_MODEL = "gemini-3.8-flash"

MASK_INSTRUCTION = """You are a privacy filter that masks sensitive data.
    Follow these steps:
    1. Identify PII and sensitive information in the text
    2. Use the mask_text tool to protect sensitive data
    3. Return ONLY the resulting text, verbatim, with no preamble, explanation,
       or commentary. If nothing needs masking, return the input text unchanged.
       Do not describe what you did or mention the tool."""


def mask_text(text: str) -> dict:
    """Mask sensitive spans with the local masker."""
    return {"masked_text": mask_sensitive_data(text)}


mask_tool = FunctionTool(func=mask_text)

mask_agent = LlmAgent(
    name="data_masker",
    model=MASK_MODEL,
    instruction=MASK_INSTRUCTION,
    description="An agent that masks sensitive data in text.",
    tools=[mask_tool],
)


async def call_mask_agent(text: str) -> str:
    """Redact ``text`` with the local masker. Does not call a cloud SDK."""
    return mask_sensitive_data(text)
