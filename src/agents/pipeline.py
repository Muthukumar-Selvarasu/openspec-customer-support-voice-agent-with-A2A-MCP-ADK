"""Judge then masker, in that order."""

from __future__ import annotations

from google.adk.agents import SequentialAgent

from src.agents.judge_agent import judge_agent
from src.agents.mask_agent import mask_agent

security_pipeline = SequentialAgent(
    name="security_pipeline",
    description="Checks input for security threats, then masks PII in the output.",
    sub_agents=[judge_agent, mask_agent],
)
