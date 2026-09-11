from helpers import get_csrf_token, register


def _enable_public_profile(client):
    html = client.get("/settings").get_data(as_text=True)
    client.post("/profile/enable", data={"csrf_token": get_csrf_token(html)})


def test_directory_excludes_private_users(client):
    register(client, "alice")
    _enable_public_profile(client)
    bob = client.application.test_client()
    register(bob, "bob")  # bob stays private

    html = client.get("/users").get_data(as_text=True)
    assert "bob" not in html


def test_directory_search_by_username(client):
    register(client, "alice")
    _enable_public_profile(client)
    bob = client.application.test_client()
    register(bob, "bob")
    _enable_public_profile(bob)

    html = client.get("/users?q=bob").get_data(as_text=True)
    assert "bob" in html

    html2 = client.get("/users?q=zzz").get_data(as_text=True)
    assert "bob" not in html2


def test_directory_sort_options_all_work(client):
    register(client, "alice")
    _enable_public_profile(client)
    bob = client.application.test_client()
    register(bob, "bob")
    _enable_public_profile(bob)

    for sort_key in ("new", "popular", "name"):
        html = client.get(f"/users?sort={sort_key}").get_data(as_text=True)
        assert "bob" in html
        assert "フォロワー" in html


def test_directory_excludes_self(client):
    register(client, "alice")
    _enable_public_profile(client)
    html = client.get("/users").get_data(as_text=True)
    # ヘッダーの自分のプロフィールリンクは常に出るので、一覧部分だけを見る
    list_section = html.split('class="user-list"')[-1] if "user-list" in html else ""
    assert "alice" not in list_section
