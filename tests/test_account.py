from helpers import add_game, get_csrf_token, login, register


def test_change_password_requires_correct_current_password(client):
    register(client, "alice")
    html = client.get("/settings").get_data(as_text=True)
    r = client.post(
        "/settings/password",
        data={
            "current_password": "wrongpass",
            "new_password": "newpassword123",
            "new_password_confirm": "newpassword123",
            "csrf_token": get_csrf_token(html),
        },
        follow_redirects=True,
    )
    assert "現在のパスワードが違うよ" in r.get_data(as_text=True)


def test_change_password_rejects_short_new_password(client):
    register(client, "alice")
    html = client.get("/settings").get_data(as_text=True)
    r = client.post(
        "/settings/password",
        data={
            "current_password": "password123",
            "new_password": "short",
            "new_password_confirm": "short",
            "csrf_token": get_csrf_token(html),
        },
        follow_redirects=True,
    )
    assert "新しいパスワードは8文字以上にしてね" in r.get_data(as_text=True)


def test_change_password_rejects_mismatched_confirmation(client):
    register(client, "alice")
    html = client.get("/settings").get_data(as_text=True)
    r = client.post(
        "/settings/password",
        data={
            "current_password": "password123",
            "new_password": "newpassword123",
            "new_password_confirm": "different123",
            "csrf_token": get_csrf_token(html),
        },
        follow_redirects=True,
    )
    assert "新しいパスワードが一致しないよ" in r.get_data(as_text=True)


def test_change_password_succeeds_and_new_password_works(client):
    register(client, "alice")
    html = client.get("/settings").get_data(as_text=True)
    client.post(
        "/settings/password",
        data={
            "current_password": "password123",
            "new_password": "newpassword123",
            "new_password_confirm": "newpassword123",
            "csrf_token": get_csrf_token(html),
        },
    )

    fresh = client.application.test_client()
    r_old = login(fresh, "alice", password="password123")
    assert "ユーザー名またはパスワードが違うよ" in r_old.get_data(as_text=True)

    fresh2 = client.application.test_client()
    r_new = login(fresh2, "alice", password="newpassword123")
    assert r_new.status_code == 302


def test_delete_account_requires_correct_password(client):
    register(client, "alice")
    add_game(client, "Elden Ring")
    html = client.get("/settings").get_data(as_text=True)
    r = client.post(
        "/settings/delete-account",
        data={"password": "wrongpass", "csrf_token": get_csrf_token(html)},
        follow_redirects=True,
    )
    assert "パスワードが違うよ" in r.get_data(as_text=True)

    # アカウントはまだ生きている
    assert client.get("/games").status_code == 200


def test_delete_account_removes_everything_and_logs_out(client, app):
    register(client, "alice")
    add_game(client, "Elden Ring")
    html = client.get("/settings").get_data(as_text=True)
    r = client.post(
        "/settings/delete-account",
        data={"password": "password123", "csrf_token": get_csrf_token(html)},
    )
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]

    # ログアウトされているので保護ページにはアクセスできない
    r2 = client.get("/games", follow_redirects=False)
    assert r2.status_code == 302
    assert "/login" in r2.headers["Location"]

    with app.app_context():
        import db

        conn = db.get_db()
        assert conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) AS c FROM games").fetchone()["c"] == 0


def test_new_user_can_register_same_username_after_deletion(client):
    register(client, "alice")
    html = client.get("/settings").get_data(as_text=True)
    client.post(
        "/settings/delete-account",
        data={"password": "password123", "csrf_token": get_csrf_token(html)},
    )

    fresh = client.application.test_client()
    r = register(fresh, "alice")
    assert r.status_code == 302
