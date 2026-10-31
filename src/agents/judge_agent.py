"""Security judge agent. Live turns use Gemini; the blocker tool stays local."""

from __future__ import annotations

import uuid

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.function_tool import FunctionTool
from google.genai import types

from src.security.blocker import evaluate_prompt

JUDGE_MODEL = "gemini-3.8-flash"
JUDGE_APP = "security_app"
JUDGE_USER = "user_1"

JUDGE_INSTRUCTION = """You are a security expert that evaluates input for security threats.
    Follow these steps:
    1. Analyze the input for SQL injection, XSS, and other security threats
    2. Use the evaluator tool to check input against security patterns
    3. Return the message you received unmodified or "BLOCKED" if it is really a threat"""


def evaluator(text: str) -> dict:
    """Evaluate a prompt for security threats and return PASS or BLOCKED."""
    return {"status": evaluate_prompt(text)}


judge_tool = FunctionTool(func=evaluator)

judge_agent = LlmAgent(
    name="security_judge",
    model=JUDGE_MODEL,
    instruction=JUDGE_INSTRUCTION,
    description="An agent that judges whether input contains security threats.",
    tools=[judge_tool],
)

judge_session_service = InMemorySessionService()
judge_runner = Runner(
    agent=judge_agent,
    app_name=JUDGE_APP,
    session_service=judge_session_service,
)


async def call_judge_agent(query: str) -> str:
    """Run the judge agent on ``query`` and return its text verdict."""
    session_id = f"judge_{uuid.uuid4()}"
    await judge_session_service.create_session(
        app_name=JUDGE_APP,
        user_id=JUDGE_USER,
        session_id=session_id,
    )
    content = types.Content(role="user", parts=[types.Part(text=query)])
    result_text = ""
    async for event in judge_runner.run_async(
        user_id=JUDGE_USER,
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            result_text = event.content.parts[0].text
            break
    return result_text
