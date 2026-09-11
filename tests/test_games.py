import re

from helpers import add_game, edit_game, get_csrf_token, register


def _first_game_id(html):
    m = re.search(r"/games/(\d+)/edit", html)
    assert m, "no game id found in list page"
    return m.group(1)


def test_create_game_requires_title(client):
    register(client, "alice")
    html = client.get("/games/new").get_data(as_text=True)
    token = get_csrf_token(html)
    r = client.post("/games/new", data={"title": "", "status": "backlog", "csrf_token": token})
    assert "タイトルは必須だよ" in r.get_data(as_text=True)


def test_create_game_rejects_invalid_status(client):
    register(client, "alice")
    html = client.get("/games/new").get_data(as_text=True)
    token = get_csrf_token(html)
    r = client.post(
        "/games/new", data={"title": "X", "status": "not-a-status", "csrf_token": token}
    )
    assert "ステータスの値が不正だよ" in r.get_data(as_text=True)


def test_create_game_rejects_rating_out_of_range(client):
    register(client, "alice")
    html = client.get("/games/new").get_data(as_text=True)
    token = get_csrf_token(html)
    r = client.post(
        "/games/new",
        data={"title": "X", "status": "backlog", "rating": "9", "csrf_token": token},
    )
    assert "評価は1〜5の範囲で入力してね" in r.get_data(as_text=True)


def test_create_game_rejects_non_numeric_rating(client):
    register(client, "alice")
    html = client.get("/games/new").get_data(as_text=True)
    token = get_csrf_token(html)
    r = client.post(
        "/games/new",
        data={"title": "X", "status": "backlog", "rating": "abc", "csrf_token": token},
    )
    assert "評価は数字で入力してね" in r.get_data(as_text=True)


def test_create_game_rejects_bad_cover_url_scheme(client):
    register(client, "alice")
    html = client.get("/games/new").get_data(as_text=True)
    token = get_csrf_token(html)
    r = client.post(
        "/games/new",
        data={
            "title": "X",
            "status": "backlog",
            "cover_url": "javascript:alert(1)",
            "csrf_token": token,
        },
    )
    assert "カバー画像のURLが不正だよ" in r.get_data(as_text=True)


def test_create_game_rejects_memo_over_max_length(client):
    register(client, "alice")
    html = client.get("/games/new").get_data(as_text=True)
    token = get_csrf_token(html)
    r = client.post(
        "/games/new",
        data={
            "title": "X",
            "status": "backlog",
            "memo": "a" * 2001,
            "csrf_token": token,
        },
    )
    assert "メモは2000文字以内にしてね" in r.get_data(as_text=True)


def test_create_and_list_game(client):
    register(client, "alice")
    r = add_game(client, "Elden Ring", status="playing", rating="5")
    assert r.status_code == 302
    html = client.get("/games").get_data(as_text=True)
    assert "Elden Ring" in html
    assert "すべて (1)" in html


def test_edit_game_updates_fields(client):
    register(client, "alice")
    add_game(client, "Stray", status="backlog")
    html = client.get("/games").get_data(as_text=True)
    game_id = _first_game_id(html)

    edit_game(client, game_id, "Stray", "completed", rating="4")
    html2 = client.get("/games").get_data(as_text=True)
    assert "クリア済み (1)" in html2


def test_delete_game_removes_it(client):
    register(client, "alice")
    add_game(client, "Hollow Knight")
    html = client.get("/games").get_data(as_text=True)
    game_id = _first_game_id(html)
    token = get_csrf_token(html)
    client.post(f"/games/{game_id}/delete", data={"csrf_token": token})
    html2 = client.get("/games").get_data(as_text=True)
    assert "Hollow Knight" not in html2
    assert "すべて (0)" in html2


def test_edit_and_delete_require_ownership(client):
    register(client, "alice")
    add_game(client, "Alices Secret Game")
    html = client.get("/games").get_data(as_text=True)
    game_id = _first_game_id(html)

    bob = client.application.test_client()
    register(bob, "bob")

    assert bob.get(f"/games/{game_id}/edit").status_code == 404

    html_bob = bob.get("/games").get_data(as_text=True)
    token = get_csrf_token(html_bob)
    bob.post(f"/games/{game_id}/delete", data={"csrf_token": token})

    # alice's game must still exist
    html_alice = client.get("/games").get_data(as_text=True)
    assert "Alices Secret Game" in html_alice


def test_export_csv_contains_own_games_only(client):
    register(client, "alice")
    add_game(client, "Elden Ring", status="playing", rating="5", memo="great game")

    bob = client.application.test_client()
    register(bob, "bob")
    add_game(bob, "Bob's Game")

    r = client.get("/export/games.csv")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert "attachment" in r.headers["Content-Disposition"]

    body = r.get_data(as_text=True)
    assert body.startswith("﻿title,status,rating,memo")
    assert "Elden Ring" in body
    assert "プレイ中" in body
    assert "great game" in body
    assert "Bob's Game" not in body


def test_export_csv_requires_login(client):
    r = client.get("/export/games.csv", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]
