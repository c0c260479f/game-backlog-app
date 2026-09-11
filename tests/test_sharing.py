import re

from helpers import add_game, get_csrf_token, register


def _share_token(html):
    m = re.search(r"/u/([\w-]+)", html)
    assert m, "share link not found"
    return m.group(1)


def test_share_disabled_by_default(client):
    register(client, "alice")
    html = client.get("/settings").get_data(as_text=True)
    assert "コレクションを共有する" in html
    assert "共有中" not in html


def test_enable_share_and_view_publicly(client):
    register(client, "alice")
    add_game(client, "Elden Ring", status="playing", rating="5", memo="secret notes")
    add_game(client, "Stray")

    html = client.get("/settings").get_data(as_text=True)
    client.post("/share/generate", data={"csrf_token": get_csrf_token(html)})

    html2 = client.get("/settings").get_data(as_text=True)
    token = _share_token(html2)

    anon = client.application.test_client()
    r = anon.get(f"/u/{token}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Elden Ring" in body
    assert "Stray" in body
    assert "secret notes" not in body  # メモは非公開
    assert "編集" not in body
    assert "削除" not in body
    assert "+ 追加" not in body


def test_invalid_share_token_is_404(client):
    register(client, "alice")
    anon = client.application.test_client()
    assert anon.get("/u/nonexistent-token").status_code == 404


def test_regenerate_invalidates_old_token(client):
    register(client, "alice")
    html = client.get("/settings").get_data(as_text=True)
    client.post("/share/generate", data={"csrf_token": get_csrf_token(html)})
    old_token = _share_token(client.get("/settings").get_data(as_text=True))

    html2 = client.get("/settings").get_data(as_text=True)
    client.post("/share/generate", data={"csrf_token": get_csrf_token(html2)})
    new_token = _share_token(client.get("/settings").get_data(as_text=True))

    assert old_token != new_token
    anon = client.application.test_client()
    assert anon.get(f"/u/{old_token}").status_code == 404
    assert anon.get(f"/u/{new_token}").status_code == 200


def test_disable_share_revokes_token(client):
    register(client, "alice")
    html = client.get("/settings").get_data(as_text=True)
    client.post("/share/generate", data={"csrf_token": get_csrf_token(html)})
    token = _share_token(client.get("/settings").get_data(as_text=True))

    html2 = client.get("/settings").get_data(as_text=True)
    client.post("/share/disable", data={"csrf_token": get_csrf_token(html2)})

    anon = client.application.test_client()
    assert anon.get(f"/u/{token}").status_code == 404


def test_share_does_not_leak_other_users_games(client):
    register(client, "alice")
    html = client.get("/settings").get_data(as_text=True)
    client.post("/share/generate", data={"csrf_token": get_csrf_token(html)})
    token = _share_token(client.get("/settings").get_data(as_text=True))

    bob = client.application.test_client()
    register(bob, "bob")
    add_game(bob, "Bob Only Game")

    anon = client.application.test_client()
    body = anon.get(f"/u/{token}").get_data(as_text=True)
    assert "Bob Only Game" not in body
