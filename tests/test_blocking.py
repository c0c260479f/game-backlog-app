from helpers import get_csrf_token, register


def _enable_public_profile(client):
    html = client.get("/settings").get_data(as_text=True)
    client.post("/profile/enable", data={"csrf_token": get_csrf_token(html)})


def _follow(follower_client, username):
    html = follower_client.get(f"/users/{username}").get_data(as_text=True)
    return follower_client.post(f"/users/{username}/follow", data={"csrf_token": get_csrf_token(html)})


def test_block_removes_mutual_follow(client, app):
    register(client, "alice")
    _enable_public_profile(client)
    bob = client.application.test_client()
    register(bob, "bob")
    _follow(bob, "alice")

    html = bob.get("/users/alice").get_data(as_text=True)
    bob.post("/users/alice/block", data={"csrf_token": get_csrf_token(html)})

    with app.app_context():
        import db

        conn = db.get_db()
        count = conn.execute("SELECT COUNT(*) AS c FROM follows").fetchone()["c"]
    assert count == 0


def test_blocked_profile_hidden_both_ways(client):
    register(client, "alice")
    _enable_public_profile(client)
    bob = client.application.test_client()
    register(bob, "bob")
    _follow(bob, "alice")

    html = bob.get("/users/alice").get_data(as_text=True)
    bob.post("/users/alice/block", data={"csrf_token": get_csrf_token(html)})

    bob_view = bob.get("/users/alice").get_data(as_text=True)
    assert "表示できないよ" in bob_view
    assert "ブロックを解除する" in bob_view  # bob blocked, so bob can unblock

    alice_view = client.get("/users/bob").get_data(as_text=True)
    assert "表示できないよ" in alice_view
    assert "ブロックを解除する" not in alice_view  # alice did not block


def test_cannot_refollow_while_blocked(client):
    register(client, "alice")
    _enable_public_profile(client)
    bob = client.application.test_client()
    register(bob, "bob")
    _follow(bob, "alice")

    html = bob.get("/users/alice").get_data(as_text=True)
    bob.post("/users/alice/block", data={"csrf_token": get_csrf_token(html)})

    r = bob.post(
        "/users/alice/follow",
        data={"csrf_token": get_csrf_token(bob.get("/users").get_data(as_text=True))},
    )
    assert r.status_code == 404


def test_blocked_users_hidden_from_directory_both_ways(client):
    register(client, "alice")
    _enable_public_profile(client)
    bob = client.application.test_client()
    register(bob, "bob")
    _enable_public_profile(bob)
    _follow(bob, "alice")

    html = bob.get("/users/alice").get_data(as_text=True)
    bob.post("/users/alice/block", data={"csrf_token": get_csrf_token(html)})

    assert "alice" not in bob.get("/users").get_data(as_text=True)
    assert "bob" not in client.get("/users").get_data(as_text=True)


def test_unblock_restores_visibility(client):
    register(client, "alice")
    _enable_public_profile(client)
    bob = client.application.test_client()
    register(bob, "bob")
    _follow(bob, "alice")

    html = bob.get("/users/alice").get_data(as_text=True)
    bob.post("/users/alice/block", data={"csrf_token": get_csrf_token(html)})

    settings_html = bob.get("/settings").get_data(as_text=True)
    assert "alice" in settings_html
    bob.post("/users/alice/unblock", data={"csrf_token": get_csrf_token(settings_html)})

    r = bob.get("/users/alice")
    assert r.status_code == 200
    assert "表示できないよ" not in r.get_data(as_text=True)
