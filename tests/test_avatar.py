from helpers import add_game, get_csrf_token, post_with_token, register


def test_set_avatar_via_url(client):
    register(client, "alice")
    html = client.get("/settings").get_data(as_text=True)
    client.post(
        "/profile/avatar",
        data={"avatar_url": "https://example.com/my-avatar.png", "csrf_token": get_csrf_token(html)},
    )
    html2 = client.get("/settings").get_data(as_text=True)
    assert "https://example.com/my-avatar.png" in html2


def test_set_avatar_rejects_invalid_scheme(client):
    register(client, "alice")
    html = client.get("/settings").get_data(as_text=True)
    client.post(
        "/profile/avatar",
        data={"avatar_url": "https://example.com/my-avatar.png", "csrf_token": get_csrf_token(html)},
    )
    html2 = client.get("/settings").get_data(as_text=True)
    client.post(
        "/profile/avatar",
        data={"avatar_url": "javascript:alert(1)", "csrf_token": get_csrf_token(html2)},
    )
    html3 = client.get("/settings").get_data(as_text=True)
    assert "javascript:alert" not in html3
    assert "https://example.com/my-avatar.png" in html3  # unchanged


def test_set_avatar_from_favorite_game(client):
    register(client, "alice")
    add_game(client, "Hollow Knight", cover_url="https://example.com/hk.jpg")
    html = client.get("/games").get_data(as_text=True)
    import re

    game_id = re.search(r"/games/(\d+)/edit", html).group(1)

    post_with_token(
        client,
        "/games",
        f"/games/{game_id}/favorite/toggle",
        {"status": "", "q": "", "sort": "updated_desc", "favorite": ""},
    )

    settings_html = client.get("/settings").get_data(as_text=True)
    assert "Hollow Knight" in settings_html  # appears in the favorite dropdown

    client.post(
        "/profile/avatar",
        data={"game_id": game_id, "csrf_token": get_csrf_token(settings_html)},
    )
    html_after = client.get("/settings").get_data(as_text=True)
    assert "https://example.com/hk.jpg" in html_after


def test_cannot_use_other_users_game_as_avatar(client):
    register(client, "alice")
    add_game(client, "Hollow Knight", cover_url="https://example.com/hk.jpg")
    html = client.get("/games").get_data(as_text=True)
    import re

    game_id = re.search(r"/games/(\d+)/edit", html).group(1)
    post_with_token(
        client,
        "/games",
        f"/games/{game_id}/favorite/toggle",
        {"status": "", "q": "", "sort": "updated_desc", "favorite": ""},
    )

    bob = client.application.test_client()
    register(bob, "bob")
    bob_settings = bob.get("/settings").get_data(as_text=True)
    bob.post(
        "/profile/avatar",
        data={"game_id": game_id, "csrf_token": get_csrf_token(bob_settings)},
    )
    bob_settings_after = bob.get("/settings").get_data(as_text=True)
    assert "https://example.com/hk.jpg" not in bob_settings_after


def test_clear_avatar(client):
    register(client, "alice")
    html = client.get("/settings").get_data(as_text=True)
    client.post(
        "/profile/avatar",
        data={"avatar_url": "https://example.com/my-avatar.png", "csrf_token": get_csrf_token(html)},
    )
    html2 = client.get("/settings").get_data(as_text=True)
    client.post("/profile/avatar/clear", data={"csrf_token": get_csrf_token(html2)})
    html3 = client.get("/settings").get_data(as_text=True)
    assert "https://example.com/my-avatar.png" not in html3
