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


def test_notifications_paginate_past_page_size(client, app):
    register(client, "alice")
    bob = client.application.test_client()
    register(bob, "bob")

    with app.app_context():
        import db

        conn = db.get_db()
        for _ in range(55):
            conn.execute(
                "INSERT INTO notifications (user_id, actor_id, kind) VALUES "
                "((SELECT id FROM users WHERE username='alice'), "
                "(SELECT id FROM users WHERE username='bob'), 'follow')"
            )
        conn.commit()

    page1 = client.get("/notifications").get_data(as_text=True)
    assert "もっと見る" in page1
    match = re.search(r"before_id=(\d+)", page1)
    assert match is not None

    page2 = client.get(f"/notifications?before_id={match.group(1)}").get_data(as_text=True)
    assert page2.count('class="notification-row') == 5
    assert "もっと見る" not in page2
