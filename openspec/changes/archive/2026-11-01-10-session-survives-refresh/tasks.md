# Tasks: `10-session-survives-refresh`

A reload keeps the signed-in shopper. Sign out still flushes immediately. A tab close flushes only after the reload window passes. Do not change `08-railway-deploy`. Do not commit until asked.

## 1. Delayed page-leave flush

- [x] 1.1 Add `PAGE_LEAVE_GRACE_MS = 3000` and `POST /api/page-leave` in `src/api/web.py`. The body is `{user_id, epoch}`. It schedules the same runner drop and one Mem0 flush as `POST /api/logout`, after the grace, and only while that epoch is still active. `POST /api/session` accepts an optional `epoch`, records it as the active epoch, cancels a scheduled flush for that user, and still returns 200 when the runner exists and 401 when it does not. `POST /api/login` and `POST /api/logout` cancel a scheduled flush for that user before they rebuild or flush. Verify with `.venv/bin/pytest tests/unit/test_session_refresh.py`: a leave whose session resume arrives inside the grace keeps the runner and does not flush; a leave with no resume drops the runner and flushes once; a resumed old epoch is ignored. Monkeypatch the grace so the test does not sleep 3 seconds. No live Mem0 call.

## 2. Shopper page restore

- [x] 2.1 On login, `src/static/index.html` stores `sessionStorage["cs-shopper"]` with `user_id`, `full_name`, `is_premium`, and `model`, and never the password. Each page view has an `epoch`. On load, a remembered shopper `POST`s `/api/session` with that user and a new epoch and does not `POST /api/login`. `200` shows the shopper name and the composer. `401` forgets the record and shows the login form. `pagehide` beacons `POST /api/page-leave` with the current epoch, and does not beacon `POST /api/logout`. A `persisted` pagehide and an open mic (`window.csVoiceOn`) do not beacon. Sign out still `POST`s `/api/logout`, forgets the record, and reloads. Verify with `.venv/bin/pytest tests/unit/test_session_refresh.py -k page`: the remembered record has no password; restore posts `/api/session` and not `/api/login`; a normal leave posts `/api/page-leave`; a frozen leave and an open mic do not.

## Workflow follow-up

- Archive this change only after apply is green and the user asks.
- Do not commit or push until the user asks.
