# Stage 1: Data Sources, Quality, Ownership & Gap Analysis (`data-audit.md`)

| Field | Details |
| :--- | :--- |
| **Engagement** | Enterprise Multi-Modal (Cascade Voice & Chat) Customer Support AI Platform |
| **FDE Stage** | Stage 1 — Discovery & Scoping |
| **Database Engine** | PostgreSQL 15+ (Local `127.0.0.1:5432` / Cloud Managed PostgreSQL on Railway or Neon via `DATABASE_URL`) |
| **External State Stores** | Mem0 Cloud API (Long-Term Memory), Arize Phoenix (OpenTelemetry Trace Store) |

---

## 1. Data Source Inventory & Ownership

| Data Store | Technology | Access Mechanism | Owner | Purpose & Lifecycle |
| :--- | :--- | :--- | :--- | :--- |
| **Customer & Order Relational DB** | PostgreSQL 15+ (`toolbox_db`) | Direct `psycopg2` (`greet.py` auth/context via `DATABASE_URL` / `PG*`) + Declarative **MCP Toolbox** (`@toolbox-sdk/server` v1.5.0 on `:5000`) | Client Order Ops / DB Admin | Stores customer credentials, tier metadata, order records, and the immutable `actions_log` audit table. |
| **Cross-Session Customer Memory** | Mem0 Platform (`mem0ai`) | Python SDK (`MemoryClient` via `MEM0_API_KEY`) | AI Platform Team | Stores semantic user preferences and conversation summaries keyed by `user_id = <email>`. Flushed once at session end. |
| **In-Process Session & Task State** | Google ADK `InMemorySessionService` & A2A `InMemoryTaskManager` | In-memory Python dictionaries (`_runners`, `_transcripts`, `tasks`) | Application Runtime | Ephemeral session history (`session_<email>`) and A2A JSON-RPC task state (`submitted → working → completed`). |
| **Telemetry & Span Store** | Arize Phoenix + OpenTelemetry | OTLP HTTP (`${PHOENIX_URL}/v1/traces`) | AI / Observability Team | Captures per-turn traces (`agent.turn`, `voice.turn`), LLM token usage, tool arguments/results, and guardrail verdicts. |

---

## 2. Relational Database Schema Audit (`toolbox_db`)

### 2.1 `users` Table
Stores shopper authentication credentials, display names, and loyalty tier metrics.

| Column | Type | Constraints | PII Classification | Audit Notes |
| :--- | :--- | :--- | :--- | :--- |
| `user_id` | `SERIAL` | `PRIMARY KEY` | Internal Identifier | Numeric PK; note that downstream session/memory APIs use `email` as canonical `user_id`. |
| `email` | `VARCHAR(255)` | `UNIQUE NOT NULL` | **Direct PII (`EMAIL_ADDRESS`)** | Primary lookup key across `customer_orders`, `actions_log`, ADK sessions, and Mem0. |
| `full_name` | `VARCHAR(100)` | Nullable | **Direct PII (`PERSON_NAME`)** | Used in personalized greetings (`Hi {full_name}!`). |
| `is_premium_customer` | `BOOLEAN` | `DEFAULT FALSE` | Business Metadata | Controls Premium tier recognition in CLI and Web header badge. |
| `total_items_purchased` | `INTEGER` | `DEFAULT 0` | Business Metadata | Displayed in CLI greeting for Premium customers. |
| `password` | `VARCHAR(255)` | `NOT NULL` | **Credential (`PASSWORD`)** | **Gap Identified:** Seeded as plaintext lowercase first name for demo simplicity. |

### 2.2 `customer_orders` Table
Stores historical and active e-commerce orders.

| Column | Type | Constraints | PII Classification | Audit Notes |
| :--- | :--- | :--- | :--- | :--- |
| `order_id` | `SERIAL` | `PRIMARY KEY` | Business Identifier | Queried by integer ID via `get-order-status`. |
| `customer_email` | `VARCHAR(100)` | `NOT NULL` | **Direct PII (`EMAIL_ADDRESS`)** | Links order to `users.email` (no formal FK constraint in seed DDL). |
| `delivery_address` | `VARCHAR(255)` | Nullable | **Direct PII (`STREET_ADDRESS`)** | High-risk PII field; must be redacted by A2A Data Masker when `MASK=true`. |
| `status` | `VARCHAR(20)` | `CHECK (status IN ('PROCESSING','SHIPPED','DELIVERED','CANCELLED','RETURNED'))` | Business State | 5 valid lifecycle states. |
| `items` | `JSONB` | Nullable | Transactional Data | JSON array of `{"product": str, "qty": int, "price": float}`. Agent must format into natural prose. |
| `order_date` | `TIMESTAMPTZ` | `DEFAULT NOW()` | Temporal Metadata | Used for `ORDER BY order_date DESC` in `find-customer-orders`. |
| `total_amount` | `DECIMAL(10,2)` | Nullable | Financial Data | Order total in USD. |

### 2.3 `actions_log` Table
Immutable audit log recording confirmed customer modification intents without mutating `customer_orders`.

| Column | Type | Constraints | PII Classification | Audit Notes |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `SERIAL` | `PRIMARY KEY` | Internal Identifier | Returned upon insert (`RETURNING id, timestamp, action_type`). |
| `timestamp` | `TIMESTAMPTZ` | `DEFAULT NOW()` | Temporal Metadata | Audit timestamp. |
| `user_email` | `VARCHAR(255)` | `NOT NULL` | **Direct PII (`EMAIL_ADDRESS`)** | Authenticated user email requesting the action. |
| `action_type` | `VARCHAR(50)` | `NOT NULL` | Audit Category | Expected values: `UPDATE_DELIVERY_ADDRESS`, `RETURN_ITEM`, `UPDATE_ORDER_STATUS`, `UPDATE_PROFILE_DETAILS`. |
| `parameters` | `JSONB` | `NOT NULL` | **Mixed / Potential PII** | Free-form JSONB payload (e.g., new delivery address, `order_id`, reason). |

---

## 3. Seeded Reference Dataset Profile

The Customer's baseline dataset (`seed.sql`) contains **10 users** and **17 orders**:

### 3.1 Customer Population (10 Accounts)
- **Premium Tier (4 users, `is_premium_customer = TRUE`):**
  1. `hannah.m@school.edu` (`Hannah M`, 94 items, password: `hannah`) — 1 order (`DELIVERED`, Order #14)
  2. `charlie.d@webmail.com` (`Charlie D`, 88 items, password: `charlie`) — 1 order (`DELIVERED`, Order #8)
  3. `julia.child@kitchen.com` (`Julia Child`, 75 items, password: `julia`) — 2 orders (`DELIVERED` #16, `PROCESSING` #17)
  4. `evan.g@bizcorp.com` (`Evan G`, 56 items, password: `evan`) — 1 order (`SHIPPED`, Order #11)
- **Standard Tier (6 users, `is_premium_customer = FALSE`):**
  5. `alice.jones@example.com` (`Alice Jones`, 42 items, password: `alice`) — 4 orders (`DELIVERED` #1 & #2, `SHIPPED` #3, `PROCESSING` #4)
  6. `ian.malcolm@chaos.com` (`Ian Malcolm`, 31 items, password: `ian`) — 1 order (`DELIVERED`, Order #15)
  7. `diana.prince@hero.net` (`Diana Prince`, 23 items, password: `diana`) — 2 orders (`DELIVERED` #9, `RETURNED` #10)
  8. `george.j@jungle.com` (`George J`, 19 items, password: `george`) — 1 order (`PROCESSING`, Order #13)
  9. `bob.smith@techmail.com` (`Bob Smith`, 15 items, password: `bob`) — 3 orders (`DELIVERED` #5, `CANCELLED` #6, `PROCESSING` #7)
  10. `fiona.shrek@swamp.com` (`Fiona Shrek`, 12 items, password: `fiona`) — 1 order (`CANCELLED`, Order #12)

### 3.2 Order Status Distribution (17 Orders)
- `DELIVERED`: 8 orders
- `PROCESSING`: 4 orders
- `SHIPPED`: 2 orders
- `CANCELLED`: 2 orders
- `RETURNED`: 1 order

---

## 4. PII Redaction Scope (16 Categories — Cloud-Agnostic)

The A2A Data Masker (`:10003`) inspects agent output across **16 PII categories**:
1. `EMAIL_ADDRESS`
2. `PHONE_NUMBER`
3. `CREDIT_CARD_NUMBER`
4. `US_SOCIAL_SECURITY_NUMBER`
5. `PERSON_NAME`
6. `IP_ADDRESS`
7. `DATE_OF_BIRTH`
8. `STREET_ADDRESS`
9. `PASSWORD`
10. `URL`
11. `AGE`
12. `VEHICLE_IDENTIFICATION_NUMBER`
13. `IBAN_CODE`
14. `MAC_ADDRESS`
15. `US_EMPLOYER_IDENTIFICATION_NUMBER`
16. `LOCATION_COORDINATES`

> **Discovery Finding on `masker.py`:** In the supplied codebase, `masker.py` relied on `google.cloud.dlp_v2` and `GOOGLE_CLOUD_PROJECT`—meaning without a GCP project and service account, it silently returned unmasked text while still incurring a 3–5 second A2A LLM round-trip. In our target build on Railway, `masker.py` will execute **self-contained deterministic PII redaction + Gemini `mask_agent` verification** so all 16 PII types are masked with asterisks (`*`) using only `GOOGLE_API_KEY`.

---

## 5. Data Quality, Connection & Schema Gaps Identified

| Gap ID | Finding in Current Codebase | Impact | Remediation Path |
| :--- | :--- | :--- | :--- |
| **DATA-GAP-01** | **Hardcoded Localhost DB Connection (`greet.py` & `tools.yaml`):** `greet.py` hardcodes `127.0.0.1:5432` (`toolbox_db` / `toolbox_user` / `mysecretpassword`), and `run.sh` writes hardcoded localhost credentials into `mcp_toolbox/tools.yaml`. | Cannot connect to managed PostgreSQL on **Railway** or **Neon** (`DATABASE_URL` / `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`). | Update `greet.py` and the `tools.yaml` generator/entrypoint to parse `DATABASE_URL` or `PG*` environment variables, defaulting to `127.0.0.1:5432` locally. |
| **DATA-GAP-02** | **Unscoped `get-order-status` SQL Query:** `SELECT ... FROM customer_orders WHERE order_id = $1;` does not filter by `customer_email`. | If User A asks for Order #5 (User B's order), PostgreSQL returns User B's row (and `web.py` streams it in the `tool_result` NDJSON event to the browser UI!) even though the LLM prompt refuses to state it in prose. | Track in OpenSpec to enforce tenant isolation at the tool/SQL boundary. |
| **DATA-GAP-03** | **Tool Parameter Naming Drift (`parameters` vs. `parameters_json`):** The MCP tool `action-log` defines the 3rd parameter as `parameters` (`tools.yaml`), whereas `prompts.py` line 56 refers to `parameters_json`. | Can cause LLM tool-call validation mismatches. | Align `prompts.py` and `tools.yaml` on `parameters`. |
| **DATA-GAP-04** | **UTF-8 Byte Offset vs. Character Slicing in Masker:** `masker.py` slices Python `str` (`masked_text[:start]`) using UTF-8 byte offsets (`byte_range.start`), which shifts indexes whenever multibyte characters (`—`, `…`, smart quotes) appear before a PII span. | Corrupts masked strings containing non-ASCII punctuation or names. | Use character-span replacement (`re.sub` / character offsets) in the self-contained masker. |
| **DATA-GAP-05** | **Destructive Re-Seed (`DROP TABLE IF EXISTS`):** `seed.sql` drops and recreates `actions_log`, `customer_orders`, and `users`. | Useful for local benchmark resets (`./run.sh seed`), but unsafe for live cloud restarts. | Use `CREATE TABLE IF NOT EXISTS` + idempotent `ON CONFLICT (email) DO NOTHING` seeding for Railway deployment startup. |
