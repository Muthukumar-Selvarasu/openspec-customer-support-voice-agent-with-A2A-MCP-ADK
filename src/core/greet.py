"""Shopper authentication, greeting, and action-log lookup against Postgres."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote_plus

import psycopg2

DEFAULT_PGHOST = "127.0.0.1"
DEFAULT_PGPORT = "5432"
DEFAULT_PGDATABASE = "toolbox_db"
DEFAULT_PGUSER = "toolbox_user"
DEFAULT_PGPASSWORD = "mysecretpassword"


def resolve_postgres_dsn() -> str:
    """Return the Postgres DSN from env, without opening a connection.

    Preference: ``DATABASE_URL``, then ``PG*`` pieces, then local Podman defaults.
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url
    host = os.getenv("PGHOST", DEFAULT_PGHOST)
    port = os.getenv("PGPORT", DEFAULT_PGPORT)
    dbname = os.getenv("PGDATABASE", DEFAULT_PGDATABASE)
    user = os.getenv("PGUSER", DEFAULT_PGUSER)
    password = os.getenv("PGPASSWORD", DEFAULT_PGPASSWORD)
    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{dbname}"
    )


def _connect():
    return psycopg2.connect(resolve_postgres_dsn())


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    """Return the matching ``users`` row, or ``None`` when credentials fail."""
    conn = None
    cur = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user_id, full_name, email, is_premium_customer, total_items_purchased
            FROM users
            WHERE email = %s AND password = %s;
            """,
            (email, password),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "full_name": row[1],
            "email": row[2],
            "is_premium_customer": row[3],
            "total_items_purchased": row[4],
        }
    except Exception:
        return None
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def greet_user(user_id: int) -> str:
    """Build the spoken greeting for an authenticated shopper."""
    conn = None
    cur = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT full_name, email, is_premium_customer, total_items_purchased
            FROM users
            WHERE user_id = %s;
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if row is None:
            return "Agent: I could not find that shopper."
        name, _email, is_premium, total_items = row
        if is_premium:
            return (
                f"Agent: Hello {name}! Welcome to the Customer Support Assistant. "
                "How can I help you today? You are a premium customer and have "
                f"{total_items} items purchased."
            )
        return (
            f"Agent: Hello {name}! Welcome to the Customer Support Assistant. "
            "How can I help you today?"
        )
    except Exception as exc:
        return f"Error: {exc}"
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def get_user_actions(email: str) -> list[dict[str, Any]]:
    """Return ``actions_log`` rows for ``email``, newest first. Empty on error."""
    conn = None
    cur = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, timestamp, action_type, parameters
            FROM actions_log
            WHERE user_email = %s
            ORDER BY timestamp DESC;
            """,
            (email,),
        )
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in rows]
    except Exception:
        return []
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()
