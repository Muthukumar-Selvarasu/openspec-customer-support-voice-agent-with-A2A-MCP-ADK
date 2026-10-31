"""Build the Judge and Masker A2A servers."""

from __future__ import annotations

from src.a2a.server import A2AServer
from src.a2a.task_manager import AgentCall, JudgeTaskManager, MaskTaskManager
from src.a2a.types import AgentCapabilities, AgentCard, AgentSkill

_CAPABILITIES = AgentCapabilities(
    streaming=True,
    pushNotifications=False,
    stateTransitionHistory=True,
)


def _card(
    *,
    name: str,
    description: str,
    host: str,
    port: int,
    skill: AgentSkill,
) -> AgentCard:
    return AgentCard(
        name=name,
        description=description,
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text", "text/plain"],
        defaultOutputModes=["text", "text/plain"],
        capabilities=_CAPABILITIES,
        skills=[skill],
    )


def create_judge_server(
    host: str = "localhost",
    port: int = 10002,
    call_judge_agent: AgentCall | None = None,
) -> A2AServer:
    """Return an A2A server whose card identifies the security-judge agent."""
    if call_judge_agent is None:
        raise ValueError("Judge agent callback function is required")
    skill = AgentSkill(
        id="security-judge",
        name="Security Threat Evaluation",
        description="Evaluates input for security threats such as SQL injection and XSS",
        tags=["security", "threat-detection", "input-validation"],
        examples=["Evaluate this input for security threats"],
    )
    return A2AServer(
        agent_card=_card(
            name="security-judge",
            description="Security judge agent that evaluates input for threats",
            host=host,
            port=port,
            skill=skill,
        ),
        task_manager=JudgeTaskManager(judge_agent_call=call_judge_agent),
        host=host,
        port=port,
    )


def create_mask_server(
    host: str = "localhost",
    port: int = 10003,
    call_mask_agent: AgentCall | None = None,
) -> A2AServer:
    """Return an A2A server for local PII masking."""
    if call_mask_agent is None:
        raise ValueError("Mask agent callback function is required")
    skill = AgentSkill(
        id="data-masker",
        name="PII Data Masking",
        description="Masks personally identifiable information in text",
        tags=["privacy", "data-protection", "pii"],
        examples=["Mask the PII in this text"],
    )
    return A2AServer(
        agent_card=_card(
            name="data-masker",
            description="Masker agent that redacts sensitive data in text",
            host=host,
            port=port,
            skill=skill,
        ),
        task_manager=MaskTaskManager(mask_agent_call=call_mask_agent),
        host=host,
        port=port,
    )
