---
name: "/opsx-fde-stage-2"
id: "opsx-fde-stage-2"
category: "Workflow"
description: "Write the Problem & Metrics pack from discovery"
---

Write the Problem & Metrics pack from Stage 0 and Stage 1.

**Planning boundary:** This command writes the three files under `docs/02-problem-metrics/` only. Do not implement application code. Do not write `src/`, `tests/`, Docker, or run `/opsx-apply`. Do not create `openspec/changes`. Do not chain into Stage 3 in the same run.

**Shared rules**

1. **OpenSpec root.** Run `openspec list --json` and read `root`. A root object means the project is set up. If `"root": null` (and it is not a store-declaration error naming this project's `openspec/config.yaml`), stop and tell the user to run `openspec init` first. Do not run `openspec init` yourself.
2. **One stage per run.** Write this stage, summarize, and stop for human review.
3. **No silent overwrite.** If any of the three output files already exist, ask: update in place, or abort. Wait for the answer. Never silently overwrite.
4. **Ground claims.** Ground every claim in `docs/ENGAGEMENT.md`, the four Stage 1 files, and customer input. Do not invent client facts, schema, SLAs, or security rules. If a fact is missing, ask or mark it unknown. Do not invent KPI targets.
5. **Metadata table.** Each output doc starts with a metadata table: Engagement, FDE Stage, Inputs, Sign-Off Owners.

**Requires:** Stage 0 + all four Stage 1 files. If any are missing, stop and name the missing path plus the command to run (`/opsx-fde-stage-0` or `/opsx-fde-stage-1`).

Required inputs:

- `docs/ENGAGEMENT.md`
- `docs/01-discovery/discovery-report.md`
- `docs/01-discovery/data-audit.md`
- `docs/01-discovery/workflow-map.md`
- `docs/01-discovery/access-security-scoping.md`

**Writes** (create `docs/02-problem-metrics/` if needed):

- `docs/02-problem-metrics/problem-brief.md`
- `docs/02-problem-metrics/success-metrics.md`
- `docs/02-problem-metrics/eval-rubric.md`

**Steps**

1. **Confirm OpenSpec is initialized** as in Shared rule 1. Stop if it is not.

2. **Confirm prior stages.** If any required input is missing, stop. Do not write Stage 2 files.

3. **Read all required inputs in full.** If Stage 1 recorded a no-go to Stage 2, stop and tell the user. Do not proceed past a recorded no-go unless the user explicitly overrides it in this request.

4. **Check for existing Stage 2 files.** If any of the three outputs already exist, ask update-in-place vs abort and wait.

5. **Write all three files.** Each file starts with:

```markdown
| Field | Value |
|---|---|
| Engagement | <from ENGAGEMENT.md> |
| FDE Stage | 2 — Problem & Metrics |
| Inputs | docs/ENGAGEMENT.md; docs/01-discovery/* |
| Sign-Off Owners | <from prior docs, or Unknown> |
```

**`problem-brief.md`**

- Core problem (from the customer problem statement and discovery findings, not a new invention)
- In scope
- Out of scope
- Constraints from discovery (data, workflow, access, security)

**`success-metrics.md`**

- Measurable KPIs covering latency, security, quality, and cost
- A target for each KPI only when the engagement, discovery, or customer input states one
- If a target was not given, record the metric with `Target: unspecified — needs customer input`. Do not invent SLAs.

**`eval-rubric.md`**

- How later PoC / QA / go-live will be scored
- Map rubric rows to the KPIs and constraints above
- Include pass/fail or score bands only when they follow from stated targets; otherwise mark them as draft pending customer sign-off

6. **Summarize and stop.** List the three files, unspecified targets, and remaining unknowns. Tell the user the next command is `/opsx-fde-stage-3` after they review. Do not run Stage 3.
