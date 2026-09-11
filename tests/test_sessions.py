import re

from helpers import add_game, register


def _first_game_id(html):
    m = re.search(r"/games/(\d+)/edit", html)
    return m.group(1)


def test_session_page_empty_state(client):
    register(client, "alice")
    add_game(client, "Elden Ring")
    game_id = _first_game_id(client.get("/games").get_data(as_text=True))
    r = client.get(f"/games/{game_id}/sessions")
    assert r.status_code == 200
    assert "まだプレイ記録がないよ" in r.get_data(as_text=True)


def test_add_session_accumulates_total(client):
    register(client, "alice")
    add_game(client, "Elden Ring")
    game_id = _first_game_id(client.get("/games").get_data(as_text=True))

    html = client.get(f"/games/{game_id}/sessions").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    client.post(
        f"/games/{game_id}/sessions",
        data={"played_on": "2026-09-01", "hours": "2", "minutes": "30", "csrf_token": token},
    )

    html2 = client.get(f"/games/{game_id}/sessions").get_data(as_text=True)
    token2 = re.search(r'name="csrf_token" value="([^"]+)"', html2).group(1)
    client.post(
        f"/games/{game_id}/sessions",
        data={"played_on": "2026-09-05", "hours": "0", "minutes": "45", "csrf_token": token2},
    )

    html3 = client.get(f"/games/{game_id}/sessions").get_data(as_text=True)
    assert "3時間15分" in html3

    # 一覧ページにも合計が出る
    list_html = client.get("/games").get_data(as_text=True)
    assert "3時間15分" in list_html


def test_session_rejects_zero_duration(client):
    register(client, "alice")
    add_game(client, "Elden Ring")
    game_id = _first_game_id(client.get("/games").get_data(as_text=True))

    html = client.get(f"/games/{game_id}/sessions").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    client.post(
        f"/games/{game_id}/sessions",
        data={"played_on": "2026-09-06", "hours": "0", "minutes": "0", "csrf_token": token},
    )
    html2 = client.get(f"/games/{game_id}/sessions").get_data(as_text=True)
    assert "2026-09-06" not in html2


def test_delete_session(client):
    register(client, "alice")
    add_game(client, "Elden Ring")
    game_id = _first_game_id(client.get("/games").get_data(as_text=True))

    html = client.get(f"/games/{game_id}/sessions").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    client.post(
        f"/games/{game_id}/sessions",
        data={"played_on": "2026-09-01", "hours": "1", "minutes": "0", "csrf_token": token},
    )

    html2 = client.get(f"/games/{game_id}/sessions").get_data(as_text=True)
    session_id = re.search(rf"/games/{game_id}/sessions/(\d+)/delete", html2).group(1)
    token2 = re.search(r'name="csrf_token" value="([^"]+)"', html2).group(1)
    client.post(
        f"/games/{game_id}/sessions/{session_id}/delete", data={"csrf_token": token2}
    )

    html3 = client.get(f"/games/{game_id}/sessions").get_data(as_text=True)
    assert "まだプレイ記録がないよ" in html3


def test_game_delete_cascades_sessions(client):
    register(client, "alice")
    add_game(client, "Elden Ring")
    html = client.get("/games").get_data(as_text=True)
    game_id = _first_game_id(html)

    session_html = client.get(f"/games/{game_id}/sessions").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', session_html).group(1)
    client.post(
        f"/games/{game_id}/sessions",
        data={"played_on": "2026-09-01", "hours": "1", "minutes": "0", "csrf_token": token},
    )

    html2 = client.get("/games").get_data(as_text=True)
    token2 = re.search(r'name="csrf_token" value="([^"]+)"', html2).group(1)
    client.post(f"/games/{game_id}/delete", data={"csrf_token": token2})

    # 削除されたゲームのセッションページはもう見えない
    assert client.get(f"/games/{game_id}/sessions").status_code == 404
