---
name: "/opsx-fde-stage-0"
id: "opsx-fde-stage-0"
category: "Workflow"
description: "Write the Client Engagement Brief from customer source material"
---

Write the Client Engagement Brief. This formats the customer's brief. It does not author the business problem.

**Planning boundary:** This command writes `docs/ENGAGEMENT.md` only. Do not implement application code. Do not write `src/`, `tests/`, Docker, or run `/opsx-apply`. Do not create `openspec/changes`. Do not chain into Stage 1 in the same run.

**Shared rules**

1. **OpenSpec root.** Run `openspec list --json` and read `root`. A root object means the project is set up. If `"root": null` (and it is not a store-declaration error naming this project's `openspec/config.yaml`), stop and tell the user to run `openspec init` first. Do not run `openspec init` yourself. Do not re-run init if a root already exists.
2. **One stage per run.** Write this stage, summarize, and stop for human review.
3. **No silent overwrite.** If `docs/ENGAGEMENT.md` already exists, ask: update in place, or abort. Wait for the answer. Never silently overwrite.
4. **Ground claims.** Ground every claim in customer source material (meeting notes, email, SOW, repo dump) or answers from a short interview. Do not invent client facts, schema, SLAs, or security rules. If a fact is missing, ask or mark it unknown.
5. **Metadata table.** The output doc starts with a metadata table: Engagement, FDE Stage, Inputs, Sign-Off Owners.

**Input:** Customer source material attached or pasted in the request, OR a short interview. If none is present, ask section by section. Do not guess.

**Writes:** `docs/ENGAGEMENT.md`  
Create `docs/` if it does not exist.

**Steps**

1. **Confirm OpenSpec is initialized** as in Shared rule 1. Stop if it is not.

2. **Collect source material.** Look in the user request, attached files, and the repo for customer notes, email, SOW, or a dump. If nothing usable is present, interview section by section using the outline below. Do not invent answers. Leave a field as `Unknown — needs customer input` only after you have asked and the user has not provided it in this run.

3. **Check for an existing brief.** If `docs/ENGAGEMENT.md` exists, ask update-in-place vs abort and wait.

4. **Write `docs/ENGAGEMENT.md`.** Start with this metadata table, then the numbered outline. Fill from customer input only.

```markdown
| Field | Value |
|---|---|
| Engagement | <client / engagement title from source> |
| FDE Stage | 0 — Client Engagement Brief |
| Inputs | <source files, notes, or interview> |
| Sign-Off Owners | <names/roles from source, or Unknown> |
```

Outline (required headings):

1. Engagement Overview (client/domain, title, architecture track, primary business goal)
2. Customer Problem Statement (why they engaged us)
3. Customer Personas & Stakeholders
4. Scope of Work (in-scope workflows, out-of-scope non-goals)
5. Customer-Provided Assets & Environment Baseline (schema, seed, tools, constraints)
6. Non-Negotiable Security, Privacy & Governance Rules
7. Expected Deliverables & Customer Acceptance Criteria

This command formats the customer's brief. It does not author the business problem. Do not turn gaps into proposed product features.

5. **Summarize and stop.** List what was written, which sections are still `Unknown`, and that Stage 0 is ready for human review. Tell the user the next command is `/opsx-fde-stage-1` after they review. Do not run Stage 1.
