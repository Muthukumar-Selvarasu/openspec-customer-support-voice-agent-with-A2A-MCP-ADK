# Proposal: Session Survives Refresh (`10-session-survives-refresh`)

## Why

Reloading `http://127.0.0.1:8000/` always returns the shopper to the login form. The signed-in shopper lives only in that page, and `pagehide` beacons `POST /api/logout`, which drops the in-memory runner. A refresh fires `pagehide` the same way a tab close does, so the next document has no session left to restore. Testers lose the conversation every time they reload to pick up a script or a container change.

## What Changes

- A reload of a signed-in tab shows that shopper again, without asking for the password, while the web process still holds the runner.
- The browser remembers the shopper profile for the tab. The password is not stored.
- The reloaded page asks the server whether that runner is still there. It does not call `POST /api/login`, so the ADK session and the unflushed transcript stay.
- If the runner is gone (process restart, or an explicit Sign out), the page shows the login form.
- **Sign out** still calls `POST /api/logout`, flushes Mem0 once, forgets the tab's shopper, and the next load shows login.
- A real tab close still flushes Mem0. `pagehide` no longer logs the shopper out immediately, because that beacon cannot tell a reload from a close. It schedules the flush, and the reloaded page cancels that schedule.
- A frozen page (`pagehide` with `persisted`) and an open mic do not schedule a flush.
- The visible chat bubbles reset to the greeting. The server-side session does not.

## Capabilities

### New Capabilities

### Modified Capabilities

- `web-and-cli-channels`: Login stays the way a shopper starts a session, and Sign out stays the single immediate Mem0 flush. A reload keeps the same server session. A tab close still flushes, after the reload has had a chance to cancel that flush.

## Impact

- `src/api/web.py` (`POST /api/session`, a delayed page-leave flush, existing `POST /api/logout`)
- `src/static/index.html` (tab shopper record, restore on load, `pagehide` no longer calls logout immediately)
- `tests/unit/test_voice.py` and a focused API test around session resume
- Discovery notes that say every `pagehide` calls `POST /api/logout` become stale; this change does not edit those docs unless a task says so

## Out of Scope

- Railway deploy (`08-railway-deploy`)
- Restoring the on-screen transcript bubbles after reload
- A cookie or server-side login token. The tab record plus the in-memory runner is the session.
- Sharing one signed-in session across two tabs. `sessionStorage` is per tab.
- Changing Explain / Quick, voice settle, or the cascade
