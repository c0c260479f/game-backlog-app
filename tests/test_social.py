import re
import sqlite3

from helpers import add_game, edit_game, get_csrf_token, post_with_token, register


def _first_game_id(html):
    return re.search(r"/games/(\d+)/edit", html).group(1)


def _enable_public_profile(client):
    html = client.get("/settings").get_data(as_text=True)
    client.post("/profile/enable", data={"csrf_token": get_csrf_token(html)})


def test_private_profile_hides_content(client):
    register(client, "alice")
    bob = client.application.test_client()
    register(bob, "bob")
    r = bob.get("/users/alice")
    assert "このプロフィールは非公開だよ" in r.get_data(as_text=True)


def test_public_profile_shows_games_and_follow_button(client):
    register(client, "alice")
    _enable_public_profile(client)
    add_game(client, "Elden Ring")

    bob = client.application.test_client()
    register(bob, "bob")
    html = bob.get("/users/alice").get_data(as_text=True)
    assert "Elden Ring" in html
    assert "フォローする" in html


def test_follow_and_unfollow(client):
    register(client, "alice")
    _enable_public_profile(client)
    bob = client.application.test_client()
    register(bob, "bob")

    html = bob.get("/users/alice").get_data(as_text=True)
    bob.post("/users/alice/follow", data={"csrf_token": get_csrf_token(html)})
    html2 = bob.get("/users/alice").get_data(as_text=True)
    assert "フォロー中" in html2

    bob.post("/users/alice/unfollow", data={"csrf_token": get_csrf_token(html2)})
    html3 = bob.get("/users/alice").get_data(as_text=True)
    assert "フォローする" in html3


def test_cannot_follow_self_or_private_user(client):
    register(client, "alice")
    _enable_public_profile(client)
    html = client.get("/users/alice").get_data(as_text=True)
    r = client.post("/users/alice/follow", data={"csrf_token": get_csrf_token(html)})
    assert r.status_code == 404

    bob = client.application.test_client()
    register(bob, "bob")  # bob stays private
    html_bob = client.get("/users/bob").get_data(as_text=True)
    r2 = client.post("/users/bob/follow", data={"csrf_token": get_csrf_token(html_bob)})
    assert r2.status_code == 404


def test_feed_shows_followed_users_activity_only(client, tmp_path):
    register(client, "alice")
    _enable_public_profile(client)
    bob = client.application.test_client()
    register(bob, "bob")
    charlie = client.application.test_client()
    register(charlie, "charlie")

    html = bob.get("/users/alice").get_data(as_text=True)
    bob.post("/users/alice/follow", data={"csrf_token": get_csrf_token(html)})

    add_game(client, "Elden Ring")

    assert "Elden Ring" in bob.get("/feed").get_data(as_text=True)
    assert "Elden Ring" not in charlie.get("/feed").get_data(as_text=True)


def test_activity_kinds_logged_added_completed_rated(client, app):
    register(client, "alice")
    add_game(client, "Elden Ring")  # -> added
    game_id = _first_game_id(client.get("/games").get_data(as_text=True))
    edit_game(client, game_id, "Elden Ring", "playing", rating="4")  # -> rated
    edit_game(client, game_id, "Elden Ring", "completed", rating="5")  # -> completed, rated

    with app.app_context():
        import db

        conn = db.get_db()
        kinds = [row["kind"] for row in conn.execute("SELECT kind FROM activities ORDER BY id")]
    assert kinds == ["added", "rated", "completed", "rated"]


def test_like_and_comment_visible_only_to_followers(client):
    register(client, "alice")
    _enable_public_profile(client)
    add_game(client, "Elden Ring")

    bob = client.application.test_client()
    register(bob, "bob")
    html = bob.get("/users/alice").get_data(as_text=True)
    bob.post("/users/alice/follow", data={"csrf_token": get_csrf_token(html)})

    charlie = client.application.test_client()
    register(charlie, "charlie")

    feed_html = bob.get("/feed").get_data(as_text=True)
    activity_id = re.search(r"/feed/(\d+)/like", feed_html).group(1)

    r_like = bob.post(f"/feed/{activity_id}/like", data={"csrf_token": get_csrf_token(feed_html)})
    assert r_like.status_code == 302
    assert "いいね 1" in bob.get("/feed").get_data(as_text=True)

    # charlieはフォローしていないので同じアクティビティにいいねできない
    charlie_feed = charlie.get("/feed").get_data(as_text=True)
    r_like_charlie = charlie.post(
        f"/feed/{activity_id}/like", data={"csrf_token": get_csrf_token(charlie_feed)}
    )
    assert r_like_charlie.status_code == 404

    feed_html2 = bob.get("/feed").get_data(as_text=True)
    bob.post(
        f"/feed/{activity_id}/comments",
        data={"body": "nice!", "csrf_token": get_csrf_token(feed_html2)},
    )
    assert "nice!" in bob.get("/feed").get_data(as_text=True)
