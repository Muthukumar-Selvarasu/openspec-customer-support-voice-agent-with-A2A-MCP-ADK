#!/usr/bin/env bash
# Local Podman orchestration for Postgres, MCP Toolbox, one A2A process,
# the web app, and optional Phoenix.
# The app image installs Python dependencies only with:
#   pip install -r requirements.txt
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Host pytest and the browser use the published port. Compose DNS is `postgres`.
HOST_DATABASE_URL="postgresql://toolbox_user:mysecretpassword@127.0.0.1:5432/toolbox_db"

compose() {
  # Keep the provider off the host Docker config. A credsStore of "desktop"
  # makes image pulls look for docker-credential-desktop, which is not required
  # for these public images.
  mkdir -p "${ROOT}/.run/docker-config"
  if [[ ! -f "${ROOT}/.run/docker-config/config.json" ]]; then
    printf '%s\n' '{}' > "${ROOT}/.run/docker-config/config.json"
  fi
  if podman compose version >/dev/null 2>&1; then
    DOCKER_CONFIG="${ROOT}/.run/docker-config" podman compose "$@"
  elif command -v podman-compose >/dev/null 2>&1; then
    DOCKER_CONFIG="${ROOT}/.run/docker-config" podman-compose "$@"
  else
    echo "podman compose is not available." >&2
    echo "If podman info fails, run: podman machine start" >&2
    exit 1
  fi
}

require_podman() {
  if ! podman info >/dev/null 2>&1; then
    echo "podman info failed. Start the machine with: podman machine start" >&2
    exit 1
  fi
}

host_port_busy() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
    return
  fi
  return 1
}

# macOS Control Center keeps host port 5000 even when AirPlay Receiver is off.
# Compose still declares "5000:5000". When that bind would fail, start from a
# runtime file that leaves Toolbox on container port 5000 without a host publish.
compose_up() {
  local file="compose.yaml"
  if host_port_busy 5000; then
    echo "Host port 5000 is in use. Toolbox listens on 0.0.0.0:5000 in the compose network and is not published on the host." >&2
    python3 - <<'PY'
from pathlib import Path
text = Path("compose.yaml").read_text(encoding="utf-8")
old = '    ports:\n      - "5000:5000"\n'
if old not in text:
    raise SystemExit("compose.yaml is missing the Toolbox host port block")
Path("compose.runtime.yaml").write_text(text.replace(old, "", 1), encoding="utf-8")
PY
    file="compose.runtime.yaml"
  else
    rm -f compose.runtime.yaml
  fi
  compose -f "$file" up -d --build postgres mcp-toolbox a2a web phoenix
}

gen_config_files() {
  mkdir -p .run
  # Compose-network catalog. Do not overwrite mcp_toolbox/tools.yaml (host 127.0.0.1).
  cat > .run/tools.yaml <<'EOF'
# Generated for the Podman compose network. Postgres host is the service name.
sources:
  cs-postgres:
    kind: postgres
    host: postgres
    port: 5432
    database: toolbox_db
    user: toolbox_user
    password: mysecretpassword

tools:
  get-order-status:
    kind: postgres-sql
    source: cs-postgres
    description: >
      Get one order for the authenticated customer. Both the order id and the
      customer email are required so another shopper's row cannot be returned
      by order id alone.
    parameters:
      - name: order_id
        type: integer
        description: The numeric order ID, for example 4.
      - name: customer_email
        type: string
        description: The authenticated customer's email, for example alice.jones@example.com.
    statement: |
      SELECT order_id, customer_email, status, delivery_address, items, order_date, total_amount
      FROM customer_orders
      WHERE order_id = $1 AND customer_email = $2;

  find-customer-orders:
    kind: postgres-sql
    source: cs-postgres
    description: >
      Find all orders for a customer by email address, most recent first.
    parameters:
      - name: email
        type: string
        description: The customer's email address, for example alice.jones@example.com.
    statement: |
      SELECT order_id, status, delivery_address, items, order_date, total_amount
      FROM customer_orders
      WHERE customer_email = $1
      ORDER BY order_date DESC;

  update-order-status:
    kind: postgres-sql
    source: cs-postgres
    description: >
      Directly update an order's status. Restricted: the support agent records
      intended changes with action-log instead of calling this tool. It stays
      in the catalog so compliance tests can see the write path.
    parameters:
      - name: order_id
        type: integer
        description: The numeric order ID.
      - name: status
        type: string
        description: New status. One of PROCESSING, SHIPPED, DELIVERED, CANCELLED, RETURNED.
    statement: |
      UPDATE customer_orders
      SET status = $2
      WHERE order_id = $1
      RETURNING order_id, status;

  action-log:
    kind: postgres-sql
    source: cs-postgres
    description: >
      Record an intended action (cancel, return, status change, address or
      profile update) for later processing. This is the mutation path the
      support agent is supposed to use.
    parameters:
      - name: user_email
        type: string
        description: The authenticated user's email.
      - name: action_type
        type: string
        description: The action type, for example CANCEL_ORDER, RETURN_ORDER, UPDATE_ADDRESS, UPDATE_PROFILE.
      - name: parameters
        type: string
        description: >
          A JSON string with the relevant context, such as order_id, the
          previous status, the requested status, items, or a new address.
    statement: |
      INSERT INTO actions_log (user_email, action_type, parameters)
      VALUES ($1, $2, $3::jsonb)
      RETURNING id, timestamp, action_type;

toolsets:
  cs_agent_tools:
    - get-order-status
    - find-customer-orders
    - update-order-status
    - action-log
EOF

  if [[ ! -f .env ]]; then
    cp .env.example .env
  fi
  if ! grep -q '^DATABASE_URL=' .env; then
    printf 'DATABASE_URL=%s\n' "$HOST_DATABASE_URL" >> .env
  fi
}

usage() {
  cat <<'EOF'
Usage: ./run.sh [setup|up|down|ps|cli]

  setup   Write .run/tools.yaml (Postgres host `postgres`) and a host .env if missing
  up      podman compose up -d (default)
  down    podman compose down
  ps      podman compose ps
  cli     podman compose run --rm cli python -m src.api.cli
EOF
}

main() {
  local cmd="${1:-up}"
  case "$cmd" in
    setup)
      gen_config_files
      ;;
    up|start)
      require_podman
      gen_config_files
      compose_up
      ;;
    down)
      require_podman
      compose down
      ;;
    ps)
      require_podman
      compose ps
      ;;
    cli)
      require_podman
      gen_config_files
      # podman compose run --rm cli python -m src.api.cli
      compose run --rm cli python -m src.api.cli
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      require_podman
      gen_config_files
      compose "$@"
      ;;
  esac
}

main "$@"
