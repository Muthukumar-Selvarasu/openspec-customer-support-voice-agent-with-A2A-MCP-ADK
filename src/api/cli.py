"""Operator CLI for the same text pipeline as the shopper web app.

``validate_input`` returns the sanitized string. ``run_turn`` passes that
string to ``runner.run``. Masked replies keep the masker's original casing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from getpass import getpass

import aiohttp
from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from tabulate import tabulate

from src.a2a.client import call_a2a_agent
from src.api.web import (
    AGENT_MODEL,
    _enforce_tenant_tool_callback,
    get_database_tools,
    resolve_service_settings,
)
from src.core.greet import authenticate_user, get_user_actions, resolve_postgres_dsn
from src.core.memory import save_memory, search_memory
from src.core.prompts import SQL_PROMPT_INSTRUCTION
from src.core.telemetry import ATTR, get_tracer
from src.security.sanitizer import sanitize_input

logger = logging.getLogger(__name__)

SHOW_TOOL_CALLS = os.getenv("CS_SHOW_TOOL_CALLS", "1") == "1"


def _fmt_tool_args(args) -> str:
    if not args:
        return ""
    try:
        return ", ".join(f"{key}={value!r}" for key, value in dict(args).items())
    except Exception:
        return str(args)


async def _check_a2a_servers() -> bool:
    settings = resolve_service_settings()
    servers = [
        ("Security Judge", settings.judge_host, settings.judge_port),
        ("Data Masker", settings.mask_host, settings.mask_port),
    ]
    all_ok = True
    for name, host, port in servers:
        url = f"http://{host}:{port}/.well-known/agent.json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        card = await resp.json()
                        print(f"  [OK] {name} agent connected  ({card.get('name', 'unknown')})")
                    else:
                        print(f"  [FAIL] {name} agent returned HTTP {resp.status}")
                        all_ok = False
        except Exception as exc:
            print(f"  [FAIL] {name} agent at {host}:{port} -- {exc}")
            all_ok = False
    return all_ok


async def validate_input(user_input: str) -> str | None:
    """Sanitize, then ask the Security Judge.

    Returns the sanitized text when both layers pass, otherwise ``None``.
    """
    tracer = get_tracer()
    settings = resolve_service_settings()
    with tracer.start_as_current_span("security.validate_input") as span:
        span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "GUARDRAIL")
        span.set_attribute(ATTR.INPUT_VALUE, user_input)
        with tracer.start_as_current_span("security.sanitize") as san_span:
            san_span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "GUARDRAIL")
            san_span.set_attribute(ATTR.INPUT_VALUE, user_input)
            try:
                clean = sanitize_input(user_input)
                san_span.set_attribute(ATTR.OUTPUT_VALUE, "passed")
            except ValueError as exc:
                san_span.set_attribute(ATTR.OUTPUT_VALUE, f"blocked: {exc}")
                print(f"\nInput rejected: {exc}")
                print("Please rephrase your question.\n")
                span.set_attribute(ATTR.OUTPUT_VALUE, "blocked")
                return None
        with tracer.start_as_current_span("security.a2a_judge") as judge_span:
            judge_span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "GUARDRAIL")
            judge_span.set_attribute(ATTR.INPUT_VALUE, clean)
            try:
                verdict = await call_a2a_agent(
                    query=clean,
                    host=settings.judge_host,
                    port=settings.judge_port,
                )
            except Exception as exc:
                judge_span.set_attribute(ATTR.OUTPUT_VALUE, f"error: {exc}")
                logger.error("Judge A2A agent call failed: %s", exc)
                print("\nError: Could not reach the Security Judge A2A agent.")
                print("Ensure A2A servers are running: python -m src.a2a.run_servers\n")
                span.set_attribute(ATTR.OUTPUT_VALUE, "blocked")
                return None
            verdict = verdict or ""
            judge_span.set_attribute(ATTR.OUTPUT_VALUE, verdict[:200])
            if "BLOCKED" in verdict.upper():
                span.set_attribute(ATTR.OUTPUT_VALUE, "blocked")
                print("\nSecurity Alert: Your input was flagged by the Security Judge agent.")
                print("Please rephrase your question in a safe manner.\n")
                return None
        span.set_attribute(ATTR.OUTPUT_VALUE, "passed")
        return clean


async def _mask_response(text: str) -> str:
    """Mask PII. The masker's casing is kept as returned."""
    tracer = get_tracer()
    settings = resolve_service_settings()
    with tracer.start_as_current_span("security.a2a_mask") as span:
        span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "GUARDRAIL")
        span.set_attribute(ATTR.INPUT_VALUE, text[:500])
        try:
            masked = await call_a2a_agent(
                query=text,
                host=settings.mask_host,
                port=settings.mask_port,
            )
        except Exception as exc:
            span.set_attribute(ATTR.OUTPUT_VALUE, f"mask_skipped: {exc}")
            logger.warning("Mask A2A agent unreachable, returning raw text: %s", exc)
            return text
        if not masked:
            span.set_attribute(ATTR.OUTPUT_VALUE, text[:500])
            return text
        span.set_attribute(ATTR.OUTPUT_VALUE, masked[:500])
        return masked


async def run_turn(runner: Runner, user_id: str, user_input: str, messages: list) -> str | None:
    """Validate, then run the agent on the sanitized string."""
    tracer = get_tracer()
    clean = await validate_input(user_input)
    if clean is None:
        return None
    messages.append({"role": "user", "content": clean})
    content = types.Content(role="user", parts=[types.Part(text=clean)])
    tool_calls_log: list[dict] = []
    tool_results_log: list[dict] = []
    masked_text = None
    with tracer.start_as_current_span("agent.turn") as turn_span:
        turn_span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "CHAIN")
        turn_span.set_attribute(ATTR.INPUT_VALUE, clean)
        turn_span.set_attribute("user.id", user_id)
        response = runner.run(
            user_id=user_id,
            session_id=f"session_{user_id}",
            new_message=content,
        )
        for event in response:
            for call in event.get_function_calls() or []:
                tool_calls_log.append({"name": call.name, "args": call.args})
                if SHOW_TOOL_CALLS:
                    print(f"  [tool] -> {call.name}({_fmt_tool_args(call.args)})")
            for result in event.get_function_responses() or []:
                resp_str = (
                    json.dumps(result.response)
                    if isinstance(result.response, dict)
                    else str(result.response)
                )
                tool_results_log.append({"name": result.name, "response": resp_str[:500]})
                if SHOW_TOOL_CALLS:
                    print(f"  [tool] <- {result.name}: {resp_str[:300]}")
                with tracer.start_as_current_span(f"tool.{result.name}") as tool_span:
                    tool_span.set_attribute(ATTR.OPENINFERENCE_SPAN_KIND, "TOOL")
                    tool_span.set_attribute(ATTR.TOOL_NAME, result.name)
                    matching = next(
                        (item for item in tool_calls_log if item["name"] == result.name),
                        {},
                    )
                    tool_span.set_attribute(
                        ATTR.INPUT_VALUE, json.dumps(matching.get("args", {}), default=str)
                    )
                    tool_span.set_attribute(ATTR.OUTPUT_VALUE, resp_str[:500])
            if event.is_final_response() and event.content and event.content.parts:
                raw_text = event.content.parts[0].text or ""
                masked_text = await _mask_response(raw_text)
                turn_span.set_attribute(ATTR.OUTPUT_VALUE, masked_text)
                print("Agent: ", masked_text)
                messages.append({"role": "assistant", "content": masked_text})
    return masked_text


def _print_known_shoppers() -> None:
    import psycopg2

    try:
        conn = psycopg2.connect(resolve_postgres_dsn())
        cur = conn.cursor()
        cur.execute("SELECT user_id, email, full_name FROM users ORDER BY user_id;")
        rows = cur.fetchall()
        headers = [desc[0] for desc in cur.description]
        print(tabulate(rows, headers=headers, tablefmt="grid"))
        cur.close()
        conn.close()
    except Exception as exc:
        print(f"Could not list shoppers: {exc}")


def _print_main_menu() -> None:
    print("\nYou can ask me to:")
    print('  1. Check the status of a specific order (e.g., "What\'s the status of order 5?").')
    print('  2. Show your order history (e.g., "Show all my past orders.").')
    print("  3. Request to cancel or return an order.")
    print("  4. Request to update your delivery address or contact details.")


async def _show_loading(message: str, dots: int = 3, delay: float = 0.4) -> None:
    print(f"\n{message}", end="", flush=True)
    for _ in range(dots):
        await asyncio.sleep(delay)
        print(".", end="", flush=True)
    print()


async def main() -> None:
    logging.getLogger().setLevel(logging.ERROR)
    print("=" * 80)
    print("Welcome to the Customer Support Assistant")
    print("=" * 80)
    print("\nConnecting to A2A agents...")
    if not await _check_a2a_servers():
        print("\nFATAL: A2A servers are not running.")
        print("Start them first:  python -m src.a2a.run_servers")
        print("Then restart this CLI.")
        return

    _print_known_shoppers()
    print("=" * 80)
    email = input("Enter your email: ").strip()
    password = getpass("Enter your password: ").strip()
    await _show_loading("[1/3] Authenticating user")
    user_context = authenticate_user(email=email, password=password)
    if not user_context:
        print("Not authorized. Exiting demo.")
        return

    user_id = user_context["email"]
    await _show_loading("[2/3] Loading current orders")
    await _show_loading("[3/3] Loading previous actions")
    actions = get_user_actions(user_id)
    if actions:
        print("\n--- Your action history ---")
        rows = [
            (
                action["id"],
                action["timestamp"],
                action["action_type"],
                str(action["parameters"])[:60]
                + ("..." if len(str(action["parameters"])) > 60 else ""),
            )
            for action in actions
        ]
        print(tabulate(rows, headers=["ID", "Time", "Action", "Details"], tablefmt="simple"))
        print()
    else:
        print("\nNo previous actions recorded.\n")

    name = user_context["full_name"]
    if user_context["is_premium_customer"]:
        print(
            f"Agent: Hello {name}! Welcome to the Customer Support Assistant. "
            "How can I help you today? You are a premium customer and have "
            f"{user_context['total_items_purchased']} items purchased."
        )
    else:
        print(
            f"Agent: Hello {name}! Welcome to the Customer Support Assistant. "
            "How can I help you today?"
        )
    _print_main_menu()

    root_agent = LlmAgent(
        model=AGENT_MODEL,
        name="customer_support_assistant",
        description="Customer support agent for order questions and requests.",
        instruction=SQL_PROMPT_INSTRUCTION.format(USER_ID=user_id),
        tools=[*get_database_tools(), search_memory],
        before_tool_callback=_enforce_tenant_tool_callback,
    )
    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, app_name="agents", session_service=session_service)
    await session_service.create_session(
        app_name="agents", user_id=user_id, session_id=f"session_{user_id}"
    )

    messages: list[dict] = []
    while True:
        print("=" * 80)
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit", "bye", "q"]:
            break
        await run_turn(runner, user_id, user_input, messages)

    if messages:
        save_memory(messages, user_id)


if __name__ == "__main__":
    asyncio.run(main())
