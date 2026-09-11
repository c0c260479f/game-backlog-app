import re

from helpers import add_game, register


def test_users_do_not_see_each_others_games(client):
    register(client, "alice")
    add_game(client, "Alice's Secret Game")

    bob = client.application.test_client()
    register(bob, "bob")
    html = bob.get("/games").get_data(as_text=True)
    assert "Alice's Secret Game" not in html
    assert "すべて (0)" in html


def test_sessions_are_scoped_to_owner(client):
    register(client, "alice")
    add_game(client, "Elden Ring")
    game_id = re.search(r"/games/(\d+)/edit", client.get("/games").get_data(as_text=True)).group(1)

    bob = client.application.test_client()
    register(bob, "bob")
    assert bob.get(f"/games/{game_id}/sessions").status_code == 404


def test_first_registered_user_inherits_ownerless_games(client, app):
    with app.app_context():
        import db

        conn = db.get_db()
        conn.execute("INSERT INTO games (title, status) VALUES ('Legacy Game', 'backlog')")
        conn.commit()

    register(client, "alice")
    html = client.get("/games").get_data(as_text=True)
    assert "Legacy Game" in html


def test_second_registered_user_does_not_inherit_ownerless_games(client, app):
    with app.app_context():
        import db

        conn = db.get_db()
        conn.execute("INSERT INTO games (title, status) VALUES ('Legacy Game', 'backlog')")
        conn.commit()

    register(client, "alice")  # first user inherits it
    bob = client.application.test_client()
    register(bob, "bob")
    html = bob.get("/games").get_data(as_text=True)
    assert "Legacy Game" not in html
