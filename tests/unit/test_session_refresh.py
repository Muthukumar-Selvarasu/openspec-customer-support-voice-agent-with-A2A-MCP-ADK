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
            "const input = { focus() {} };",
            "const document = {",
            "  getElementById(id) {",
            "    if (id === 'login') return loginEl.removed ? null : loginEl;",
            "    if (id === 'logout') return logoutEl;",
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
    assert result["normal"]["url"] == "/api/page-leave"
    assert result["normal"]["body"]["epoch"] == "epoch-live"
    assert result["frozen"] is None
    assert result["mic"] is None
    assert result["forgot"] is None
