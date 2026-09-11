from helpers import register

import core
from blueprints import games as games_bp


def test_search_returns_empty_without_api_key(client, monkeypatch):
    monkeypatch.setattr(core, "RAWG_API_KEY", None)
    register(client, "alice")
    r = client.get("/api/games/search?q=zelda")
    assert r.status_code == 200
    assert r.get_json() == []


def test_search_returns_empty_for_short_query(client, monkeypatch):
    monkeypatch.setattr(core, "RAWG_API_KEY", "dummy-key")
    register(client, "alice")
    r = client.get("/api/games/search?q=a")
    assert r.get_json() == []


def test_search_requires_login(client):
    r = client.get("/api/games/search?q=zelda", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_search_parses_rawg_response_and_filters_blank_names(client, monkeypatch):
    monkeypatch.setattr(core, "RAWG_API_KEY", "dummy-key")
    register(client, "alice")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "results": [
                    {"name": "Elden Ring", "background_image": "https://example.com/elden.jpg"},
                    {"name": "", "background_image": "https://example.com/noname.jpg"},
                    {"name": "Hollow Knight", "background_image": None},
                ]
            }

    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return FakeResponse()

    monkeypatch.setattr(games_bp.requests, "get", fake_get)

    r = client.get("/api/games/search?q=elden ring")
    data = r.get_json()
    assert data == [
        {"name": "Elden Ring", "cover_url": "https://example.com/elden.jpg"},
        {"name": "Hollow Knight", "cover_url": None},
    ]
    assert captured["params"]["search"] == "elden ring"


def test_search_swallows_network_errors(client, monkeypatch):
    monkeypatch.setattr(core, "RAWG_API_KEY", "dummy-key")
    register(client, "alice")

    def raising_get(url, params=None, timeout=None):
        raise games_bp.requests.RequestException("network down")

    monkeypatch.setattr(games_bp.requests, "get", raising_get)

    r = client.get("/api/games/search?q=elden ring")
    assert r.status_code == 200
    assert r.get_json() == []
