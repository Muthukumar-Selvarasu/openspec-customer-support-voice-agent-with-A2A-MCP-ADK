---
name: "/opsx-fde-stage-3"
id: "opsx-fde-stage-3"
category: "Workflow"
description: "Write the Proof of Concept pack and stop for /opsx-propose"
---

Write the Proof of Concept pack from Stages 0–2. This is a paper/plan PoC unless the user provides empirical results. Stage 4 is not a custom command: after this stage, the user runs stock `/opsx-propose`.

**Planning boundary:** This command writes the three files under `docs/03-poc/` only. Do not implement application code. Do not write `src/`, `tests/`, Docker, or run `/opsx-apply`. Do not create `openspec/changes`. Do not start `/opsx-propose`. Do not chain into propose in the same run.

**Shared rules**

1. **OpenSpec root.** Run `openspec list --json` and read `root`. A root object means the project is set up. If `"root": null` (and it is not a store-declaration error naming this project's `openspec/config.yaml`), stop and tell the user to run `openspec init` first. Do not run `openspec init` yourself.
2. **One stage per run.** Write this stage, summarize, and stop for human review.
3. **No silent overwrite.** If any of the three output files already exist, ask: update in place, or abort. Wait for the answer. Never silently overwrite.
4. **Ground claims.** Ground every claim in Stages 0–2 and customer input. Do not invent client facts, schema, SLAs, or security rules. Do not fake pass/fail numbers.
5. **Metadata table.** Each output doc starts with a metadata table: Engagement, FDE Stage, Inputs, Sign-Off Owners.

**Requires:** Stage 0 + Stage 1 + Stage 2 files. If any are missing, stop and name the missing path plus the command to run.

Required inputs:

- `docs/ENGAGEMENT.md`
- `docs/01-discovery/discovery-report.md`
- `docs/01-discovery/data-audit.md`
- `docs/01-discovery/workflow-map.md`
- `docs/01-discovery/access-security-scoping.md`
- `docs/02-problem-metrics/problem-brief.md`
- `docs/02-problem-metrics/success-metrics.md`
- `docs/02-problem-metrics/eval-rubric.md`

**Writes** (create `docs/03-poc/` if needed):

- `docs/03-poc/poc-plan.md`
- `docs/03-poc/poc-validation-log.md`
- `docs/03-poc/poc-demo-notes.md`

**Steps**

1. **Confirm OpenSpec is initialized** as in Shared rule 1. Stop if it is not.

2. **Confirm prior stages.** If any required input is missing, stop. Do not write Stage 3 files.

3. **Read all required inputs in full.** Use the problem brief, metrics, and rubric as the PoC frame.

4. **Check for existing Stage 3 files.** If any of the three outputs already exist, ask update-in-place vs abort and wait.

5. **Write all three files.** Each file starts with:

```markdown
| Field | Value |
|---|---|
| Engagement | <from ENGAGEMENT.md> |
| FDE Stage | 3 — Proof of Concept |
| Inputs | docs/ENGAGEMENT.md; docs/01-discovery/*; docs/02-problem-metrics/*; <empirical results if provided> |
| Sign-Off Owners | <from prior docs, or Unknown> |
```

**`poc-plan.md`**

- Hypotheses (tied to the problem brief and KPIs)
- Sandbox topology (env-configurable URLs/hosts/ports with localhost defaults unless the customer specified otherwise)
- Scripted scenarios (from the workflow map and eval rubric)
- Label this a **paper/plan PoC** unless the user provided empirical results from a live run

**`poc-validation-log.md`**

- Results
- Defects
- Explicit GO/NO-GO to `/opsx-propose`
- If no live run happened, label each finding **paper / inspection** vs **empirical**. Do not fake pass/fail numbers. A paper GO means "the plan is coherent enough to propose the first slice," not "the system passed tests."

**`poc-demo-notes.md`**

- What to show the customer
- Scenario order
- What is in-scope for the first independently testable slice vs later work
- Open questions to confirm in the demo

6. **Summarize and stop.** List the three files and the GO/NO-GO. Then tell the user:

> Review Stage 3. When you are ready, run `/opsx-propose <change-id>` for the first independently testable slice.

Do not start OpenSpec propose. Do not write `src/`. Stage 4 is stock `/opsx-propose`, not a custom FDE command.
