import re

from helpers import add_game, get_csrf_token, register


def _enable_public_profile(client):
    html = client.get("/settings").get_data(as_text=True)
    client.post("/profile/enable", data={"csrf_token": get_csrf_token(html)})


def test_follow_creates_notification(client):
    register(client, "alice")
    _enable_public_profile(client)
    bob = client.application.test_client()
    register(bob, "bob")

    html = bob.get("/users/alice").get_data(as_text=True)
    bob.post("/users/alice/follow", data={"csrf_token": get_csrf_token(html)})

    alice_games = client.get("/games").get_data(as_text=True)
    assert "notification-badge" in alice_games

    notif_html = client.get("/notifications").get_data(as_text=True)
    assert "bob" in notif_html
    assert "フォローされたよ" in notif_html


def test_visiting_notifications_marks_as_read(client):
    register(client, "alice")
    _enable_public_profile(client)
    bob = client.application.test_client()
    register(bob, "bob")
    html = bob.get("/users/alice").get_data(as_text=True)
    bob.post("/users/alice/follow", data={"csrf_token": get_csrf_token(html)})

    client.get("/notifications")
    html_after = client.get("/games").get_data(as_text=True)
    assert "notification-badge" not in html_after


def test_like_and_comment_create_notifications(client):
    register(client, "alice")
    _enable_public_profile(client)
    add_game(client, "Elden Ring")

    bob = client.application.test_client()
    register(bob, "bob")
    html = bob.get("/users/alice").get_data(as_text=True)
    bob.post("/users/alice/follow", data={"csrf_token": get_csrf_token(html)})

    feed_html = bob.get("/feed").get_data(as_text=True)
    activity_id = re.search(r"/feed/(\d+)/like", feed_html).group(1)
    bob.post(f"/feed/{activity_id}/like", data={"csrf_token": get_csrf_token(feed_html)})

    feed_html2 = bob.get("/feed").get_data(as_text=True)
    bob.post(
        f"/feed/{activity_id}/comments",
        data={"body": "nice!", "csrf_token": get_csrf_token(feed_html2)},
    )

    notif_html = client.get("/notifications").get_data(as_text=True)
    assert "いいねしたよ" in notif_html
    assert "コメントしたよ" in notif_html


def test_self_actions_do_not_notify(client, app):
    register(client, "alice")
    add_game(client, "Elden Ring")
    feed_html = client.get("/feed").get_data(as_text=True)
    activity_id = re.search(r"/feed/(\d+)/like", feed_html).group(1)
    client.post(f"/feed/{activity_id}/like", data={"csrf_token": get_csrf_token(feed_html)})

    with app.app_context():
        import db

        conn = db.get_db()
        count = conn.execute("SELECT COUNT(*) AS c FROM notifications").fetchone()["c"]
    assert count == 0
