# Design: Session Survives Refresh

## Context

See `proposal.md` for why. `POST /api/login` in `src/api/web.py` builds an in-memory runner and resets the ADK session. `POST /api/logout` pops that runner and flushes `_transcripts` to Mem0 once. The shopper page keeps `USER` in the document and, on `pagehide`, beacons `POST /api/logout`. A reload fires that beacon, so the next document finds no runner and shows the login form. The working tree already remembers a shopper profile in `sessionStorage` and exposes `POST /api/session`, but a normal reload still beacons logout, so the restore sees 401. No new host or port is involved.

## Goals / Non-Goals

**Goals:**

- The same tab can reload and stay on that shopper while the runner is still in this process.
- Sign out and a tab that does not come back still flush Mem0 once.
- Restore must not call `POST /api/login`.

**Non-Goals:**

- Painting the previous bubbles again. The new document shows the greeting.
- A shared login across tabs, or a cookie.

## Decisions

### Decision 1: The tab remembers the profile, and the server still owns the session

On a successful login the page writes `sessionStorage["cs-shopper"]` with `user_id`, `full_name`, `is_premium`, and `model`. It does not write the password. On load, if that record exists, the page `POST`s `/api/session`. `200` enters the shop. `401` deletes the record and leaves the login form. Restore does not post email and password, so login's session reset does not run.

Alternative: call `POST /api/login` again from the stored password. Rejected. That would store the password and wipe the ADK session on every reload.

### Decision 2: pagehide schedules a flush, and the next document cancels it

`pagehide` cannot tell a reload from a tab close. The beacon stops calling `POST /api/logout`.

Each page view has an `epoch` string, stored in `sessionStorage` and sent with both calls. `POST /api/page-leave` with `{user_id, epoch}` schedules the same flush as logout after `PAGE_LEAVE_GRACE_MS` (3000), and only if that epoch is still the active one. `POST /api/session` with `{user_id, epoch}` records the new epoch as active, cancels a scheduled flush for that user, and returns whether the runner exists. A beacon that arrives after the new page has already resumed carries the old epoch and is ignored.

`LogoutReq` gains an optional `epoch`. Callers that omit it still work. `POST /api/logout` and `POST /api/login` cancel any scheduled flush for that user before they flush or rebuild, so Sign out cannot be followed by a second flush, and a new login cannot be undone by an old leave.

A `pagehide` whose `persisted` flag is true does not schedule a flush. An open mic (`window.csVoiceOn`) does not either. Those leaves are not a tab close.

Alternative: delete the beacon and flush only on Sign out. Rejected. Discovery treats tab close as a Mem0 flush, and dropping it would discard `_transcripts` on the next login.

### Decision 3: Tests drive the grace with a monkeypatch

`PAGE_LEAVE_GRACE_MS` is a module constant, not an environment variable. Unit tests set it to a few tens of milliseconds. They do not sleep for three seconds and they do not call Mem0. A page test loads the shopper script in Node and checks that a non-persisted leave beacons `/api/page-leave`, that a persisted leave and an open mic do not, and that restore posts `/api/session` rather than `/api/login`.

## Risks / Trade-offs

- **[Risk] The beacon arrives before the resumed page, and the grace expires during a slow reload** → Mitigation: 3000 ms is enough for a local reload. The resume cancels the task as soon as `/api/session` runs.
- **[Risk] Two views share one runner and one view's leave flushes the other** → Mitigation: out of scope. `sessionStorage` is per tab. A duplicated tab can still share the runner; the last un-cancelled leave wins.
- **[Risk] The on-screen transcript disappears and looks like a new chat** → Mitigation: the spec only requires the shopper and the composer. The ADK session remains because restore does not log in again.

## Migration Plan

No data migration. Ship `src/api/web.py` and `src/static/index.html` together. A running Podman web container serves the new page after the next image rebuild. Rollback is reverting this change. `08-railway-deploy` is untouched.

## Open Questions

None. The storage key, the grace, and the two endpoints are fixed by the specs and the decisions above.
