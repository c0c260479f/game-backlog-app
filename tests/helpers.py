import re

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def get_csrf_token(html):
    match = CSRF_RE.search(html)
    assert match, "CSRF token not found in page"
    return match.group(1)


def register(client, username, password="password123"):
    html = client.get("/register").get_data(as_text=True)
    token = get_csrf_token(html)
    return client.post(
        "/register",
        data={
            "username": username,
            "password": password,
            "password_confirm": password,
            "csrf_token": token,
        },
    )


def login(client, username, password="password123"):
    html = client.get("/login").get_data(as_text=True)
    token = get_csrf_token(html)
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": token},
    )


def add_game(client, title, status="backlog", rating="", cover_url="", memo=""):
    html = client.get("/games/new").get_data(as_text=True)
    token = get_csrf_token(html)
    return client.post(
        "/games/new",
        data={
            "title": title,
            "status": status,
            "rating": rating,
            "cover_url": cover_url,
            "memo": memo,
            "csrf_token": token,
        },
    )


def edit_game(client, game_id, title, status, rating="", cover_url="", memo=""):
    html = client.get(f"/games/{game_id}/edit").get_data(as_text=True)
    token = get_csrf_token(html)
    return client.post(
        f"/games/{game_id}/edit",
        data={
            "title": title,
            "status": status,
            "rating": rating,
            "cover_url": cover_url,
            "memo": memo,
            "csrf_token": token,
        },
    )


def post_with_token(client, get_url, post_url, data=None):
    """get_urlのページからCSRFトークンを取り、post_urlへPOSTする"""
    html = client.get(get_url).get_data(as_text=True)
    token = get_csrf_token(html)
    payload = dict(data or {})
    payload["csrf_token"] = token
    return client.post(post_url, data=payload)
