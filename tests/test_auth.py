from helpers import get_csrf_token, login, register


def test_register_creates_account_and_logs_in(client):
    r = register(client, "alice")
    assert r.status_code == 302
    r2 = client.get("/games")
    assert r2.status_code == 200


def test_register_rejects_invalid_username(client):
    html = client.get("/register").get_data(as_text=True)
    token = get_csrf_token(html)
    r = client.post(
        "/register",
        data={
            "username": "a b!",
            "password": "password123",
            "password_confirm": "password123",
            "csrf_token": token,
        },
    )
    assert "ユーザー名は半角英数字" in r.get_data(as_text=True)


def test_register_rejects_short_password(client):
    html = client.get("/register").get_data(as_text=True)
    token = get_csrf_token(html)
    r = client.post(
        "/register",
        data={
            "username": "shortpw",
            "password": "short",
            "password_confirm": "short",
            "csrf_token": token,
        },
    )
    assert "8文字以上" in r.get_data(as_text=True)


def test_register_rejects_password_mismatch(client):
    html = client.get("/register").get_data(as_text=True)
    token = get_csrf_token(html)
    r = client.post(
        "/register",
        data={
            "username": "mismatch",
            "password": "password123",
            "password_confirm": "different123",
            "csrf_token": token,
        },
    )
    assert "パスワードが一致しないよ" in r.get_data(as_text=True)


def test_register_rejects_duplicate_username(client):
    register(client, "dupeuser")
    fresh = client.application.test_client()
    html = fresh.get("/register").get_data(as_text=True)
    token = get_csrf_token(html)
    r = fresh.post(
        "/register",
        data={
            "username": "dupeuser",
            "password": "password123",
            "password_confirm": "password123",
            "csrf_token": token,
        },
    )
    assert "既に使われているよ" in r.get_data(as_text=True)


def test_login_wrong_password_shows_error(client):
    register(client, "bob")
    fresh = client.application.test_client()
    html = fresh.get("/login").get_data(as_text=True)
    token = get_csrf_token(html)
    r = fresh.post(
        "/login",
        data={"username": "bob", "password": "wrongpass", "csrf_token": token},
    )
    assert "ユーザー名またはパスワードが違うよ" in r.get_data(as_text=True)


def test_login_correct_password_succeeds(client):
    register(client, "carol")
    fresh = client.application.test_client()
    r = login(fresh, "carol")
    assert r.status_code == 302
    assert fresh.get("/games").status_code == 200


def test_anonymous_access_redirects_to_login(client):
    r = client.get("/games", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_logout_then_protected_route_redirects(client):
    register(client, "dave")
    html = client.get("/games").get_data(as_text=True)
    token = get_csrf_token(html)
    client.post("/logout", data={"csrf_token": token})
    r = client.get("/games", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_login_is_rate_limited_after_repeated_attempts(client):
    register(client, "erin")
    fresh = client.application.test_client()

    statuses = []
    for _ in range(11):
        html = fresh.get("/login").get_data(as_text=True)
        token = get_csrf_token(html)
        r = fresh.post(
            "/login",
            data={"username": "erin", "password": "wrongpass", "csrf_token": token},
        )
        statuses.append(r.status_code)

    # 「10 per minute」の設定なので、11回目は429で弾かれるはず
    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429
