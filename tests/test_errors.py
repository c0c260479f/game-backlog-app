from helpers import get_csrf_token, register


def test_404_shows_custom_page(client):
    r = client.get("/this-page-does-not-exist")
    assert r.status_code == 404
    assert "ページが見つからないよ" in r.get_data(as_text=True)


def test_csrf_failure_shows_custom_400_page(client):
    register(client, "alice")
    # わざとCSRFトークンなしでPOSTする
    r = client.post("/games/new", data={"title": "X", "status": "backlog"})
    assert r.status_code == 400
    assert "リクエストが正しくないよ" in r.get_data(as_text=True)


def test_rate_limit_shows_custom_429_page(client):
    register(client, "erin")
    fresh = client.application.test_client()

    last = None
    for _ in range(11):
        html = fresh.get("/login").get_data(as_text=True)
        token = get_csrf_token(html)
        last = fresh.post(
            "/login",
            data={"username": "erin", "password": "wrongpass", "csrf_token": token},
        )

    assert last.status_code == 429
    assert "ちょっと待って" in last.get_data(as_text=True)


def test_security_headers_present(client):
    r = client.get("/login")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "same-origin"
