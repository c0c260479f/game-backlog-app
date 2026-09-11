import re

from helpers import add_game, post_with_token, register


def _game_ids_in_order(html):
    return re.findall(r"/games/(\d+)/edit", html)


def _titles_in_order(html):
    return re.findall(r'<h2 class="game-title">\s*(?:<span[^>]*>[^<]*</span>\s*)?([^<]+?)\s*</h2>', html)


def test_search_finds_matching_title_only(client):
    register(client, "alice")
    add_game(client, "Elden Ring")
    add_game(client, "Stray")

    html = client.get("/games?q=ring").get_data(as_text=True)
    assert "Elden Ring" in html
    assert "Stray" not in html


def test_search_escapes_like_wildcards(client):
    register(client, "alice")
    add_game(client, "100%_Orange_Juice")
    add_game(client, "Elden Ring")

    html = client.get("/games?q=100%25").get_data(as_text=True)
    assert "100%_Orange_Juice" in html
    assert "Elden Ring" not in html


def test_no_match_shows_dedicated_message(client):
    register(client, "alice")
    add_game(client, "Stray")
    html = client.get("/games?q=zzz_no_match").get_data(as_text=True)
    assert "一致するゲームは見つからなかったよ" in html


def test_sort_orders_are_stable_even_with_tied_timestamps(client):
    register(client, "alice")
    add_game(client, "First")
    add_game(client, "Second")

    html = client.get("/games?sort=updated_desc").get_data(as_text=True)
    titles = _titles_in_order(html)
    # 後から登録した方が「更新日が新しい順」で先頭に来るはず
    assert titles.index("Second") < titles.index("First")


def test_sort_title_asc(client):
    register(client, "alice")
    add_game(client, "Zelda")
    add_game(client, "Alpha")
    html = client.get("/games?sort=title_asc").get_data(as_text=True)
    titles = _titles_in_order(html)
    assert titles.index("Alpha") < titles.index("Zelda")


def test_favorite_toggle_and_filter(client):
    register(client, "alice")
    add_game(client, "Stray")
    add_game(client, "Hollow Knight")
    html = client.get("/games").get_data(as_text=True)
    ids = _game_ids_in_order(html)
    hk_id = ids[0]  # 新しい順なのでHollow Knightが先頭

    post_with_token(
        client,
        "/games",
        f"/games/{hk_id}/favorite/toggle",
        {"status": "", "q": "", "sort": "updated_desc", "favorite": ""},
    )

    html2 = client.get("/games").get_data(as_text=True)
    assert "favorite-star" in html2

    fav_only = client.get("/games?favorite=1").get_data(as_text=True)
    assert "Hollow Knight" in fav_only
    assert "Stray" not in fav_only

    # トグルで解除
    post_with_token(
        client,
        "/games",
        f"/games/{hk_id}/favorite/toggle",
        {"status": "", "q": "", "sort": "updated_desc", "favorite": ""},
    )
    fav_only2 = client.get("/games?favorite=1").get_data(as_text=True)
    assert "お気に入りに登録したゲームがまだないよ" in fav_only2
