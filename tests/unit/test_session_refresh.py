"""Reload cancels a page-leave flush. A leave that nobody resumes still flushes once."""

import time

import pytest
from fastapi.testclient import TestClient

import src.api.web as web

SHOPPER = "alice.jones@example.com"


def _reset() -> None:
    for task in list(web._leave_tasks.values()):
        if not task.done():
            task.cancel()
    web._leave_tasks.clear()
    web._active_epoch.clear()
    web._runners.clear()
    web._transcripts.clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    saved: list[tuple] = []

    def save(messages, user_id):
        saved.append((list(messages), user_id))
        return {"status": "success"}

    _reset()
    monkeypatch.setattr(web, "PAGE_LEAVE_GRACE_MS", 40)
    monkeypatch.setattr(web, "save_memory", save)
    web._runners[SHOPPER] = object()
    web._transcripts[SHOPPER] = [{"role": "user", "content": "hi hello"}]
    with TestClient(web.app) as http:
        http.saved = saved  # type: ignore[attr-defined]
        yield http
    _reset()


def _leave(client: TestClient, epoch: str) -> None:
    response = client.post("/api/page-leave", json={"user_id": SHOPPER, "epoch": epoch})
    assert response.status_code == 200


def _resume(client: TestClient, epoch: str) -> None:
    response = client.post("/api/session", json={"user_id": SHOPPER, "epoch": epoch})
    assert response.status_code == 200


def test_resume_inside_the_grace_keeps_the_runner(client: TestClient) -> None:
    _leave(client, "epoch-a")
    _resume(client, "epoch-b")
    time.sleep(0.2)
    assert SHOPPER in web._runners
    assert client.saved == []  # type: ignore[attr-defined]


def test_leave_with_no_resume_flushes_once(client: TestClient) -> None:
    _leave(client, "epoch-a")
    time.sleep(0.2)
    assert SHOPPER not in web._runners
    assert len(client.saved) == 1  # type: ignore[attr-defined]
    assert client.saved[0][1] == SHOPPER  # type: ignore[attr-defined]
    assert client.saved[0][0][0]["content"] == "hi hello"  # type: ignore[attr-defined]


def test_old_epoch_after_resume_is_ignored(client: TestClient) -> None:
    _resume(client, "epoch-new")
    _leave(client, "epoch-old")
    time.sleep(0.2)
    assert SHOPPER in web._runners
    assert client.saved == []  # type: ignore[attr-defined]


def test_session_without_a_runner_is_401(client: TestClient) -> None:
    web._runners.pop(SHOPPER, None)
    missing = client.post("/api/session", json={"user_id": "nobody@example.com"})
    assert missing.status_code == 401


def test_login_returns_agent_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset()
    monkeypatch.setattr(
        web,
        "authenticate_user",
        lambda email, password: {
            "user_id": 1,
            "email": SHOPPER,
            "full_name": "Alice Jones",
            "is_premium_customer": True,
            "total_items_purchased": 4,
        },
    )
    monkeypatch.setattr(web, "get_database_tools", lambda: [])
    with TestClient(web.app) as http:
        resp = http.post("/api/login", json={"email": SHOPPER, "password": "alice"})
    _reset()
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["model"] == web.AGENT_MODEL


def _page_script() -> str:
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "src" / "static" / "index.html"
    ).read_text(encoding="utf-8")
    record_start = source.index("const SHOPPER_KEY=")
    record_end = source.index("async function login(", record_start)
    leave_start = source.index("function shouldFlushOnPageHide(")
    leave_end = source.index("restoreShopper();", leave_start)
    return "\n".join(
        [
            "var USER = null;",
            "const store = new Map();",
            "const sessionStorage = {",
            "  setItem(key, value) { store.set(key, String(value)); },",
            "  getItem(key) { return store.has(key) ? store.get(key) : null; },",
            "  removeItem(key) { store.delete(key); },",
            "};",
            "const posts = [];",
            "let sessionOk = true;",
            "function fetch(url, opts) {",
            "  const body = JSON.parse(opts.body);",
            "  posts.push({ url, body });",
            "  const ok = url === '/api/session' && sessionOk;",
            "  return Promise.resolve({ ok, status: ok ? 200 : 401, json: async () => ({ ok: true }) });",
            "}",
            "const who = { textContent: '' };",
            "const footer = { style: { display: 'none' } };",
            "const loginEl = { removed: false, remove() { this.removed = true; } };",
            "const logoutEl = { style: { display: 'none' } };",
            "const demoModeEl = { style: { display: 'none' } };",
            "const guardrailEl = { style: { display: 'none' } };",
            "const input = { focus() {} };",
            "const document = {",
            "  getElementById(id) {",
            "    if (id === 'login') return loginEl.removed ? null : loginEl;",
            "    if (id === 'logout') return logoutEl;",
            "    if (id === 'demoMode') return demoModeEl;",
            "    if (id === 'guardrailToggles') return guardrailEl;",
            "    if (id === 'input') return input;",
            "    return null;",
            "  },",
            "  querySelector() { return null; },",
            "};",
            "const col = { appendChild() {} };",
            "function el() { return {}; }",
            "function esc(value) { return value; }",
            "function renderChips() {}",
            "const window = {",
            "  csVoiceOn: false,",
            "  crypto: { randomUUID: () => 'epoch-live' },",
            "  addEventListener() {},",
            "  dispatchEvent() {},",
            "};",
            source[record_start:record_end],
            source[leave_start:leave_end],
        ]
    )


def test_page_record_omits_the_password() -> None:
    import json
    import subprocess

    script = "\n".join(
        [
            _page_script(),
            "rememberShopper({",
            "  user_id: 'alice.jones@example.com',",
            "  full_name: 'Alice Jones',",
            "  is_premium: true,",
            "  model: 'gemini',",
            "  password: 'alice'",
            "});",
            "const record = JSON.parse(sessionStorage.getItem('cs-shopper'));",
            "console.log(JSON.stringify({ keys: Object.keys(record), password: record.password || null }));",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["password"] is None
    assert "password" not in result["keys"]


def test_page_restore_confirms_session_and_leave_does_not_log_out() -> None:
    import json
    import subprocess

    script = "\n".join(
        [
            _page_script(),
            "sessionStorage.setItem('cs-shopper', JSON.stringify({",
            "  user_id: 'alice.jones@example.com', full_name: 'Alice Jones', is_premium: true, model: ''",
            "}));",
            "restoreShopper().then(() => {",
            "  const kept = {",
            "    posts: posts.map((post) => post.url),",
            "    body: posts[0] && posts[0].body,",
            "    who: who.textContent,",
            "    footer: footer.style.display,",
            "    login: loginEl.removed,",
            "    demo: demoModeEl.style.display,",
            "    guard: guardrailEl.style.display,",
            "  };",
            "  epoch = 'epoch-live';",
            "  USER = 'alice.jones@example.com';",
            "  const normal = pageLeaveRequest({ persisted: false });",
            "  const frozen = pageLeaveRequest({ persisted: true });",
            "  window.csVoiceOn = true;",
            "  const mic = pageLeaveRequest({ persisted: false });",
            "  sessionOk = false;",
            "  sessionStorage.setItem('cs-shopper', JSON.stringify({ user_id: 'alice.jones@example.com' }));",
            "  return restoreShopper().then(() => {",
            "    console.log(JSON.stringify({ kept, normal, frozen, mic, forgot: sessionStorage.getItem('cs-shopper') }));",
            "  });",
            "}).catch((err) => { console.error(err); process.exit(1); });",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["kept"]["posts"] == ["/api/session"]
    assert "/api/login" not in result["kept"]["posts"]
    assert result["kept"]["body"]["user_id"] == "alice.jones@example.com"
    assert result["kept"]["body"]["epoch"]
    assert "Alice Jones" in result["kept"]["who"]
    assert result["kept"]["footer"] == "block"
    assert result["kept"]["login"] is True
    assert result["kept"]["demo"] == "flex"
    assert result["kept"]["guard"] == "flex"
    assert result["normal"]["url"] == "/api/page-leave"
    assert result["normal"]["body"]["epoch"] == "epoch-live"
    assert result["frozen"] is None
    assert result["mic"] is None
    assert result["forgot"] is None


def test_page_leave_allowed_after_ptt_turn_pauses_idle() -> None:
    import json
    import subprocess
    from pathlib import Path

    ui_source = (Path(__file__).resolve().parents[2] / "src" / "voice" / "ui.js").read_text(
        encoding="utf-8"
    )
    ptt_start = ui_source.index("function clearPttTail(")
    ptt_end = ui_source.index("function onFrame(", ptt_start)
    script = "\n".join(
        [
            _page_script(),
            "USER = 'alice.jones@example.com';",
            "epoch = 'epoch-ptt';",
            "const PTT_RELEASE_TAIL_MS = 1000;",
            "let muted = false;",
            "let pttActive = false;",
            "let pttDownAt = 0;",
            "let pttReleased = false;",
            "let pttPaused = true;",
            "let pttTailTimer = null;",
            "let speaking = false;",
            "let agentSpeaking = false;",
            "let turnRunning = false;",
            "let ignoreAudio = false;",
            "let frames = [];",
            "let preroll = [];",
            "let silentFrames = 0;",
            "let onsetCount = 0;",
            "let tailCb = null;",
            "function setTimeout(fn) { tailCb = fn; return 7; }",
            "function clearTimeout() { tailCb = null; }",
            "function now() { return 1000; }",
            "function bargeIn() {}",
            "function sendInterrupt() {}",
            "function sendFrame() {}",
            "function setVoiceStatus() {}",
            "function endUtterance() { speaking = false; }",
            ui_source[ptt_start:ptt_end],
            "beginPtt();",
            "const leaveDuringCapture = pageLeaveRequest({ persisted: false });",
            "releasePtt();",
            "const leaveDuringTail = pageLeaveRequest({ persisted: false });",
            "tailCb();",
            "const leaveAfterIdle = pageLeaveRequest({ persisted: false });",
            "console.log(JSON.stringify({ leaveDuringCapture, leaveDuringTail, leaveAfterIdle }));",
        ]
    )
    proc = subprocess.run(["node", "-"], input=script, text=True, capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["leaveDuringCapture"] is None
    assert result["leaveDuringTail"] is None
    assert result["leaveAfterIdle"] == {
        "url": "/api/page-leave",
        "body": {"user_id": "alice.jones@example.com", "epoch": "epoch-ptt"},
    }
