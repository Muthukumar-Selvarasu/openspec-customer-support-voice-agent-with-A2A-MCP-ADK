"""Start the Judge and Masker A2A servers on env-configured addresses."""

from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)

DEFAULT_JUDGE_HOST = "localhost"
DEFAULT_JUDGE_PORT = 10002
DEFAULT_MASK_HOST = "localhost"
DEFAULT_MASK_PORT = 10003


def _env_text(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_port(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value.strip())


def bind_addresses() -> tuple[str, int, str, int]:
    """Resolve Judge and Masker bind addresses from the environment.

    Unset or blank ``A2A_JUDGE_HOST`` / ``A2A_JUDGE_PORT`` /
    ``A2A_MASK_HOST`` / ``A2A_MASK_PORT`` fall back to
    ``localhost:10002`` and ``localhost:10003``.
    """
    return (
        _env_text("A2A_JUDGE_HOST", DEFAULT_JUDGE_HOST),
        _env_port("A2A_JUDGE_PORT", DEFAULT_JUDGE_PORT),
        _env_text("A2A_MASK_HOST", DEFAULT_MASK_HOST),
        _env_port("A2A_MASK_PORT", DEFAULT_MASK_PORT),
    )


def resolve_server_binds(
    judge_host: str | None = None,
    judge_port: int | None = None,
    mask_host: str | None = None,
    mask_port: int | None = None,
) -> tuple[str, int, str, int]:
    """Apply explicit overrides on top of :func:`bind_addresses`."""
    env_judge_host, env_judge_port, env_mask_host, env_mask_port = bind_addresses()
    return (
        env_judge_host if judge_host is None else judge_host,
        env_judge_port if judge_port is None else judge_port,
        env_mask_host if mask_host is None else mask_host,
        env_mask_port if mask_port is None else mask_port,
    )


def _run_server(server) -> None:
    import uvicorn

    logger.info("Starting server on %s:%s", server.host, server.port)
    uvicorn.run(server.app, host=server.host, port=server.port)


def start_all_servers(
    judge_host: str | None = None,
    judge_port: int | None = None,
    mask_host: str | None = None,
    mask_port: int | None = None,
) -> list[threading.Thread]:
    """Start Judge and Masker in daemon threads. Does not block."""
    from src.agents.judge_agent import call_judge_agent
    from src.agents.mask_agent import call_mask_agent
    from src.a2a.factories import create_judge_server, create_mask_server

    judge_host, judge_port, mask_host, mask_port = resolve_server_binds(
        judge_host, judge_port, mask_host, mask_port
    )
    servers = [
        create_judge_server(
            host=judge_host,
            port=judge_port,
            call_judge_agent=call_judge_agent,
        ),
        create_mask_server(
            host=mask_host,
            port=mask_port,
            call_mask_agent=call_mask_agent,
        ),
    ]
    threads: list[threading.Thread] = []
    for server in servers:
        thread = threading.Thread(target=_run_server, args=(server,), daemon=True)
        thread.start()
        threads.append(thread)
    logger.info("A2A servers started (Judge :%s, Masker :%s)", judge_port, mask_port)
    return threads


def main() -> None:
    """Bind both servers from the environment and wait until interrupted."""
    from dotenv import load_dotenv

    load_dotenv()
    threads = start_all_servers()
    logger.info("Press Ctrl+C to stop.")
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        logger.info("Shutting down servers.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
