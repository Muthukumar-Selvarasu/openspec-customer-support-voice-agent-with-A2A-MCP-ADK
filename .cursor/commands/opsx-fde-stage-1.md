---
name: "/opsx-fde-stage-1"
id: "opsx-fde-stage-1"
category: "Workflow"
description: "Run Discovery & Scoping from the engagement brief"
---

Run Discovery & Scoping. Produce the four Stage 1 documents from `docs/ENGAGEMENT.md` and the real repo when present.

**Planning boundary:** This command writes the four files under `docs/01-discovery/` only. Do not implement application code. Do not write `src/`, `tests/`, Docker, or run `/opsx-apply`. Do not create `openspec/changes`. Do not write `docs/ENGAGEMENT.md`. Do not chain into Stage 2 in the same run.

**Shared rules**

1. **OpenSpec root.** Run `openspec list --json` and read `root`. A root object means the project is set up. If `"root": null` (and it is not a store-declaration error naming this project's `openspec/config.yaml`), stop and tell the user to run `openspec init` first. Do not run `openspec init` yourself.
2. **One stage per run.** Write this stage, summarize, and stop for human review.
3. **No silent overwrite.** If any of the four output files already exist, ask: update in place, or abort. Wait for the answer. Never silently overwrite.
4. **Ground claims.** Ground every claim in `docs/ENGAGEMENT.md`, customer input, and what you actually inspect in the repo. Do not invent client facts, schema, SLAs, or security rules. If a fact is missing, ask or mark it unknown.
5. **Metadata table.** Each output doc starts with a metadata table: Engagement, FDE Stage, Inputs, Sign-Off Owners.

**Requires:** `docs/ENGAGEMENT.md` exists. If it is missing, stop and tell the user to run `/opsx-fde-stage-0` first.

**Writes** (create `docs/01-discovery/` if needed):

- `docs/01-discovery/discovery-report.md`
- `docs/01-discovery/data-audit.md`
- `docs/01-discovery/workflow-map.md`
- `docs/01-discovery/access-security-scoping.md`

**Steps**

1. **Confirm OpenSpec is initialized** as in Shared rule 1. Stop if it is not.

2. **Confirm Stage 0.** If `docs/ENGAGEMENT.md` is missing, stop and tell the user to run `/opsx-fde-stage-0`.

3. **Read `docs/ENGAGEMENT.md` in full.** Use it as the source of customer facts. Do not contradict it without quoting the conflict and asking the user.

4. **Inspect the repo (read-only).** Look at application code, configs, existing DB/tools, and docs outside `openspec/` when they exist. If the repo has no application (`src/` empty or absent, no running services, no schema), say so in the discovery report and work only from `docs/ENGAGEMENT.md`. Do not invent a codebase.

5. **Check for existing Stage 1 files.** If any of the four outputs already exist, ask update-in-place vs abort and wait.

6. **Write all four files.** Each file starts with:

```markdown
| Field | Value |
|---|---|
| Engagement | <from ENGAGEMENT.md> |
| FDE Stage | 1 — Discovery & Scoping |
| Inputs | docs/ENGAGEMENT.md; <repo paths inspected, or "repo empty — engagement only"> |
| Sign-Off Owners | <from ENGAGEMENT.md, or Unknown> |
```

**`discovery-report.md`**

- Findings (what exists vs what the engagement describes)
- Current systems
- Gaps
- Stage 1 go/no-go to Stage 2, with the evidence used. Do not rubber-stamp GO if required facts are unknown.

**`data-audit.md`**

- Sources
- Quality
- Ownership
- Schema and gaps vs engagement assets (`docs/ENGAGEMENT.md` section 5)

**`workflow-map.md`**

- As-is customer workflows
- To-be customer workflows
- Across channels named in the engagement (voice, chat, email, ticket, and any others actually listed). Do not add channels that were not named.

**`access-security-scoping.md`**

- Access
- Network
- Security
- Compliance
- Tenancy

Mark unknowns explicitly. Do not invent security rules.

7. **Summarize and stop.** List the four files, the go/no-go recommendation, and remaining unknowns. Tell the user the next command is `/opsx-fde-stage-2` after they review. Do not run Stage 2.
