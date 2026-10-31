"""File-level contracts for the database and MCP foundation slice.

Live Postgres checks run only under ``postgres_podman`` so the rest of the
file stays green without a container.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

LOCAL_PACKAGES = (
    "google-adk",
    "toolbox-core",
    "mem0ai",
    "fastapi",
    "psycopg2-binary",
    "pytest",
    "pytest-asyncio",
    "httpx",
    "pyyaml",
    "arize-phoenix",
    "openinference-instrumentation-google-genai",
    "openinference-semantic-conventions",
)

PINNED_PACKAGES = (
    "opentelemetry-sdk==1.42.1",
    "opentelemetry-api==1.42.1",
    "opentelemetry-exporter-otlp-proto-http==1.42.1",
    "opentelemetry-semantic-conventions==0.63b1",
)

FORBIDDEN_PACKAGES = (
    "google-cloud-dlp",
    "google-cloud-secret-manager",
    "google-auth",
)

ENV_KEYS = (
    "GOOGLE_API_KEY",
    "MEM0_API_KEY",
    "MASK",
    "AGENT_RESPONSE_STREAM",
    "TELEMETRY",
    "DATABASE_URL",
    "TOOLBOX_URL",
    "A2A_JUDGE_HOST",
    "A2A_JUDGE_PORT",
    "A2A_MASK_HOST",
    "A2A_MASK_PORT",
    "PHOENIX_URL",
    "PHOENIX_PUBLIC_URL",
    "HOST",
    "PORT",
    "WEB_PORT",
)

FORBIDDEN_ENV_KEYS = (
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "MODEL_ARMOR_TEMPLATE_ID",
)

ORDER_STATUSES = ("PROCESSING", "SHIPPED", "DELIVERED", "CANCELLED", "RETURNED")
TOOL_NAMES = (
    "get-order-status",
    "find-customer-orders",
    "action-log",
    "update-order-status",
)


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _requirement_names(requirements: str) -> set[str]:
    names: set[str] = set()
    for raw in requirements.splitlines():
        line = raw.split("#", 1)[0].strip().lower()
        if not line:
            continue
        match = re.match(r"([a-z0-9][a-z0-9._-]*)", line)
        if match:
            names.add(match.group(1))
    return names


def _sql_tuples(sql: str, table: str) -> list[str]:
    match = re.search(
        rf"INSERT INTO {table}\b.*?VALUES\s*(.*?);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing INSERT INTO {table}"
    return re.findall(r"\((?:[^()]|\([^()]*\))*\)", match.group(1))


def test_requirements_list_local_packages_and_omit_leftovers() -> None:
    requirements = _text("requirements.txt")
    lowered = requirements.lower()
    names = _requirement_names(requirements)
    for package in LOCAL_PACKAGES:
        assert package in names, package
    for pin in PINNED_PACKAGES:
        assert pin in lowered, pin
    for leftover in FORBIDDEN_PACKAGES:
        assert leftover not in names, leftover


def test_env_example_documents_localhost_defaults() -> None:
    env = _text(".env.example")
    for key in ENV_KEYS:
        assert re.search(rf"^{re.escape(key)}=", env, flags=re.MULTILINE), key
    for leftover in FORBIDDEN_ENV_KEYS:
        assert not re.search(rf"^{re.escape(leftover)}=", env, flags=re.MULTILINE)
    assert "postgresql://toolbox_user:mysecretpassword@127.0.0.1:5432/toolbox_db" in env
    assert "http://127.0.0.1:5000" in env
    assert "localhost:10002" in env or (
        re.search(r"^A2A_JUDGE_HOST=localhost$", env, flags=re.MULTILINE)
        and re.search(r"^A2A_JUDGE_PORT=10002$", env, flags=re.MULTILINE)
    )
    assert re.search(r"^A2A_MASK_HOST=localhost$", env, flags=re.MULTILINE)
    assert re.search(r"^A2A_MASK_PORT=10003$", env, flags=re.MULTILINE)
    assert "http://localhost:6006" in env
    assert re.search(r"^HOST=127\.0\.0\.1$", env, flags=re.MULTILINE)
    assert re.search(r"^PORT=8000$", env, flags=re.MULTILINE)
    assert re.search(r"^WEB_PORT=8000$", env, flags=re.MULTILINE)
    alias_note = re.search(r"WEB_PORT.*alias of PORT", env, flags=re.IGNORECASE)
    assert alias_note, "WEB_PORT must be documented as an alias of PORT"


def test_seed_defines_tables_and_demo_shoppers() -> None:
    sql = _text("mcp_toolbox/seed.sql")
    for table in ("users", "customer_orders", "actions_log"):
        assert re.search(rf"CREATE TABLE {table}\b", sql), table
    users = _sql_tuples(sql, "users")
    orders = _sql_tuples(sql, "customer_orders")
    assert len(users) == 10
    assert sum(1 for row in users if re.search(r"\bTRUE\b", row)) == 4
    assert sum(1 for row in users if re.search(r"\bFALSE\b", row)) == 6
    assert len(orders) == 17
    for status in ORDER_STATUSES:
        assert any(f"'{status}'" in row for row in orders), status
    assert "REFERENCES users (email)" in sql
    assert "customer_orders_customer_email_idx" in sql


def test_tools_catalog_scopes_order_lookup_to_the_customer() -> None:
    catalog = yaml.safe_load(_text("mcp_toolbox/tools.yaml"))
    lookup = catalog["tools"]["get-order-status"]
    parameters = [item["name"] for item in lookup["parameters"]]
    assert parameters == ["order_id", "customer_email"]
    statement = " ".join(lookup["statement"].split())
    assert "WHERE order_id = $1 AND customer_email = $2" in statement
    assert set(catalog["toolsets"]["cs_agent_tools"]) == set(TOOL_NAMES)
    for name in TOOL_NAMES:
        assert catalog["tools"][name]["kind"] == "postgres-sql"
        assert catalog["tools"][name]["source"] == "cs-postgres"
    source = catalog["sources"]["cs-postgres"]
    assert source["host"] == "127.0.0.1"
    assert source["port"] == 5432
    assert source["database"] == "toolbox_db"
    assert source["user"] == "toolbox_user"


def test_compose_declares_postgres_service() -> None:
    compose = yaml.safe_load(_text("compose.yaml"))
    service = compose["services"]["postgres"]
    assert "postgres" in str(service["image"])
    assert service["environment"]["POSTGRES_DB"] == "toolbox_db"
    assert service["environment"]["POSTGRES_USER"] == "toolbox_user"
    assert service["environment"]["POSTGRES_PASSWORD"] == "mysecretpassword"
    assert "5432:5432" in service["ports"]


def _podman(*args: str) -> subprocess.CompletedProcess[str]:
    podman = shutil.which("podman")
    if podman is None:
        pytest.skip("podman is not on PATH")
    return subprocess.run(
        [podman, *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_postgres_podman_seed_counts() -> None:
    info = _podman("info")
    if info.returncode != 0:
        pytest.skip(f"podman info failed: {info.stderr.strip()}")
    query = _podman(
        "compose",
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "toolbox_user",
        "-d",
        "toolbox_db",
        "-tAc",
        "SELECT (SELECT count(*) FROM users), (SELECT count(*) FROM customer_orders);",
    )
    if query.returncode != 0:
        pytest.skip(f"postgres is not ready: {query.stderr.strip()}")
    counts = query.stdout.strip()
    assert counts == "10|17", counts
