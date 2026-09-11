import datetime
import os
import re
import secrets

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

import auth
import db
from auth import User

load_dotenv()

RAWG_API_KEY = os.environ.get("RAWG_API_KEY")
RAWG_SEARCH_URL = "https://api.rawg.io/api/games"

STATUS_LABELS = {
    "backlog": "積みゲー",
    "playing": "プレイ中",
    "completed": "クリア済み",
}
VALID_STATUSES = set(STATUS_LABELS.keys())

SORT_OPTIONS = {
    "updated_desc": ("更新日が新しい順", "g.updated_at DESC, g.id DESC"),
    "created_desc": ("登録日が新しい順", "g.created_at DESC, g.id DESC"),
    "rating_desc": ("評価が高い順", "g.rating IS NULL, g.rating DESC, g.id DESC"),
    "title_asc": ("タイトル順", "g.title COLLATE NOCASE ASC, g.id ASC"),
    "playtime_desc": ("プレイ時間が長い順", "total_minutes DESC, g.id DESC"),
}
DEFAULT_SORT = "updated_desc"

USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,20}$")

ACTIVITY_KIND_LABELS = {
    "added": "を積みゲーに追加したよ",
    "completed": "をクリアしたよ",
    "rated": "を評価したよ",
}

DIRECTORY_SORT_OPTIONS = {
    "new": ("新着順", "u.created_at DESC, u.id DESC"),
    "popular": ("人気順", "follower_count DESC, u.id DESC"),
    "name": ("名前順", "u.username COLLATE NOCASE ASC"),
}
DEFAULT_DIRECTORY_SORT = "new"


def _fetch_games(user_id, status_filter, search_query, sort_key, favorite_only=False):
    """指定ユーザーのゲーム一覧を、絞り込み・検索・並び替え条件に沿って取得する"""
    conn = db.get_db()

    conditions = ["g.user_id = ?"]
    params = [user_id]
    if status_filter in VALID_STATUSES:
        conditions.append("g.status = ?")
        params.append(status_filter)
    if favorite_only:
        conditions.append("g.is_favorite = 1")
    if search_query:
        conditions.append("g.title LIKE ? ESCAPE '\\'")
        escaped = search_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{escaped}%")

    where_clause = f"WHERE {' AND '.join(conditions)}"
    order_clause = SORT_OPTIONS[sort_key][1]

    games = conn.execute(
        f"""SELECT g.*, COALESCE(SUM(ps.minutes), 0) AS total_minutes
            FROM games g
            LEFT JOIN play_sessions ps ON ps.game_id = g.id
            {where_clause}
            GROUP BY g.id
            ORDER BY {order_clause}""",
        params,
    ).fetchall()

    counts = {
        row["status"]: row["c"]
        for row in conn.execute(
            "SELECT status, COUNT(*) AS c FROM games WHERE user_id = ? GROUP BY status",
            (user_id,),
        ).fetchall()
    }
    return games, counts


def format_minutes(total_minutes):
    """分数を「12時間30分」のような表示用文字列に変換する"""
    if not total_minutes:
        return None
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours}時間{minutes}分"
    if hours:
        return f"{hours}時間"
    return f"{minutes}分"


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    db.init_app(app)
    auth.init_app(app)
    CSRFProtect(app)

    @app.context_processor
    def inject_globals():
        unread_notification_count = 0
        if current_user.is_authenticated:
            conn = db.get_db()
            unread_notification_count = conn.execute(
                "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND is_read = 0",
                (int(current_user.id),),
            ).fetchone()["c"]
        return {
            "STATUS_LABELS": STATUS_LABELS,
            "format_minutes": format_minutes,
            "ACTIVITY_KIND_LABELS": ACTIVITY_KIND_LABELS,
            "unread_notification_count": unread_notification_count,
        }

    @app.route("/")
    def index():
        return redirect(url_for("game_list"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("game_list"))

        username = ""
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            password_confirm = request.form.get("password_confirm", "")

            error = None
            if not username or not password:
                error = "ユーザー名とパスワードは必須だよ。"
            elif not USERNAME_RE.match(username):
                error = "ユーザー名は半角英数字・_・-のみ、3〜20文字にしてね。"
            elif len(password) < 8:
                error = "パスワードは8文字以上にしてね。"
            elif password != password_confirm:
                error = "パスワードが一致しないよ。"

            conn = db.get_db()
            if error is None:
                existing = conn.execute(
                    "SELECT id FROM users WHERE username = ?", (username,)
                ).fetchone()
                if existing is not None:
                    error = "そのユーザー名は既に使われているよ。"

            if error is not None:
                flash(error)
                return render_template("auth/register.html", username=username)

            cur = conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            )
            conn.commit()
            new_user_id = cur.lastrowid

            # 最初のユーザー登録なら、まだ所有者のいない既存ゲームをこのユーザーのものにする
            user_count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
            if user_count == 1:
                conn.execute(
                    "UPDATE games SET user_id = ? WHERE user_id IS NULL", (new_user_id,)
                )
                conn.commit()

            login_user(User(new_user_id, username))
            return redirect(url_for("game_list"))

        return render_template("auth/register.html", username=username)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("game_list"))

        username = ""
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            conn = db.get_db()
            row = conn.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?",
                (username,),
            ).fetchone()

            if row is None or not check_password_hash(row["password_hash"], password):
                flash("ユーザー名またはパスワードが違うよ。")
                return render_template("auth/login.html", username=username)

            login_user(User(row["id"], row["username"]))
            next_url = request.args.get("next")
            return redirect(next_url or url_for("game_list"))

        return render_template("auth/login.html", username=username)

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/games")
    @login_required
    def game_list():
        status_filter = request.args.get("status", "all")
        if status_filter not in VALID_STATUSES:
            status_filter = "all"

        search_query = request.args.get("q", "").strip()

        sort_key = request.args.get("sort", DEFAULT_SORT)
        if sort_key not in SORT_OPTIONS:
            sort_key = DEFAULT_SORT

        favorite_only = request.args.get("favorite") == "1"

        games, counts = _fetch_games(
            int(current_user.id), status_filter, search_query, sort_key, favorite_only
        )

        return render_template(
            "games/list.html",
            games=games,
            status_filter=status_filter,
            search_query=search_query,
            sort_key=sort_key,
            sort_options=SORT_OPTIONS,
            counts=counts,
            total=sum(counts.values()),
            favorite_only=favorite_only,
        )

    @app.route("/games/<int:game_id>/favorite/toggle", methods=["POST"])
    @login_required
    def game_favorite_toggle(game_id):
        conn = db.get_db()
        conn.execute(
            "UPDATE games SET is_favorite = 1 - is_favorite WHERE id = ? AND user_id = ?",
            (game_id, int(current_user.id)),
        )
        conn.commit()
        return redirect(
            url_for(
                "game_list",
                status=request.form.get("status") or None,
                q=request.form.get("q") or None,
                sort=request.form.get("sort") or None,
                favorite=request.form.get("favorite") or None,
            )
        )

    @app.route("/settings")
    @login_required
    def settings():
        conn = db.get_db()
        user_row = conn.execute(
            "SELECT username, share_token, is_public, avatar_url FROM users WHERE id = ?",
            (int(current_user.id),),
        ).fetchone()
        share_url = (
            url_for("public_list", token=user_row["share_token"], _external=True)
            if user_row["share_token"]
            else None
        )
        profile_url = (
            url_for("user_profile", username=user_row["username"], _external=True)
            if user_row["is_public"]
            else None
        )
        favorite_games = conn.execute(
            """SELECT id, title, cover_url FROM games
               WHERE user_id = ? AND is_favorite = 1 AND cover_url IS NOT NULL
               ORDER BY title COLLATE NOCASE ASC""",
            (int(current_user.id),),
        ).fetchall()
        blocked_users = conn.execute(
            """SELECT u.id, u.username FROM blocks b
               JOIN users u ON u.id = b.blocked_id
               WHERE b.blocker_id = ?
               ORDER BY u.username COLLATE NOCASE ASC""",
            (int(current_user.id),),
        ).fetchall()
        return render_template(
            "settings.html",
            share_url=share_url,
            profile_url=profile_url,
            is_public=bool(user_row["is_public"]),
            avatar_url=user_row["avatar_url"],
            favorite_games=favorite_games,
            blocked_users=blocked_users,
        )

    @app.route("/profile/avatar", methods=["POST"])
    @login_required
    def profile_avatar_update():
        conn = db.get_db()
        user_id = int(current_user.id)
        game_id = request.form.get("game_id", "").strip()
        avatar_url = request.form.get("avatar_url", "").strip()

        if game_id:
            game = conn.execute(
                "SELECT cover_url FROM games WHERE id = ? AND user_id = ? AND is_favorite = 1",
                (game_id, user_id),
            ).fetchone()
            if game is None or not game["cover_url"]:
                flash("そのゲームの画像は使えないよ。")
                return redirect(url_for("settings"))
            new_avatar_url = game["cover_url"]
        elif avatar_url:
            if not (avatar_url.startswith("http://") or avatar_url.startswith("https://")):
                flash("画像のURLが不正だよ。")
                return redirect(url_for("settings"))
            new_avatar_url = avatar_url
        else:
            flash("画像URLを入力するか、お気に入りゲームを選んでね。")
            return redirect(url_for("settings"))

        conn.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (new_avatar_url, user_id))
        conn.commit()
        return redirect(url_for("settings"))

    @app.route("/profile/avatar/clear", methods=["POST"])
    @login_required
    def profile_avatar_clear():
        conn = db.get_db()
        conn.execute(
            "UPDATE users SET avatar_url = NULL WHERE id = ?", (int(current_user.id),)
        )
        conn.commit()
        return redirect(url_for("settings"))

    @app.route("/share/generate", methods=["POST"])
    @login_required
    def share_generate():
        conn = db.get_db()
        token = secrets.token_urlsafe(24)
        conn.execute(
            "UPDATE users SET share_token = ? WHERE id = ?", (token, int(current_user.id))
        )
        conn.commit()
        return redirect(url_for("settings"))

    @app.route("/share/disable", methods=["POST"])
    @login_required
    def share_disable():
        conn = db.get_db()
        conn.execute(
            "UPDATE users SET share_token = NULL WHERE id = ?", (int(current_user.id),)
        )
        conn.commit()
        return redirect(url_for("settings"))

    @app.route("/profile/enable", methods=["POST"])
    @login_required
    def profile_enable():
        conn = db.get_db()
        conn.execute(
            "UPDATE users SET is_public = 1 WHERE id = ?", (int(current_user.id),)
        )
        conn.commit()
        return redirect(url_for("settings"))

    @app.route("/profile/disable", methods=["POST"])
    @login_required
    def profile_disable():
        conn = db.get_db()
        conn.execute(
            "UPDATE users SET is_public = 0 WHERE id = ?", (int(current_user.id),)
        )
        conn.commit()
        return redirect(url_for("settings"))

    @app.route("/users")
    @login_required
    def user_directory():
        search_query = request.args.get("q", "").strip()
        sort_key = request.args.get("sort", DEFAULT_DIRECTORY_SORT)
        if sort_key not in DIRECTORY_SORT_OPTIONS:
            sort_key = DEFAULT_DIRECTORY_SORT

        conn = db.get_db()
        user_id = int(current_user.id)

        conditions = ["u.is_public = 1", "u.id != ?"]
        params = [user_id]
        if search_query:
            conditions.append("u.username LIKE ? ESCAPE '\\'")
            escaped = search_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
        conditions.append(
            """u.id NOT IN (
                   SELECT blocked_id FROM blocks WHERE blocker_id = ?
                   UNION
                   SELECT blocker_id FROM blocks WHERE blocked_id = ?
               )"""
        )
        params.extend([user_id, user_id])

        order_clause = DIRECTORY_SORT_OPTIONS[sort_key][1]

        users_rows = conn.execute(
            f"""SELECT u.id, u.username, u.avatar_url,
                       (SELECT COUNT(*) FROM follows f WHERE f.followee_id = u.id) AS follower_count
                FROM users u
                WHERE {' AND '.join(conditions)}
                ORDER BY {order_clause}""",
            params,
        ).fetchall()

        following_ids = {
            row["followee_id"]
            for row in conn.execute(
                "SELECT followee_id FROM follows WHERE follower_id = ?",
                (user_id,),
            ).fetchall()
        }

        return render_template(
            "social/users.html",
            users=users_rows,
            following_ids=following_ids,
            search_query=search_query,
            sort_key=sort_key,
            sort_options=DIRECTORY_SORT_OPTIONS,
        )

    @app.route("/users/<username>")
    @login_required
    def user_profile(username):
        conn = db.get_db()
        profile_user = conn.execute(
            "SELECT id, username, is_public, avatar_url FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if profile_user is None:
            abort(404)

        is_own_profile = int(current_user.id) == profile_user["id"]

        if not is_own_profile and _is_blocked(conn, int(current_user.id), profile_user["id"]):
            blocked_by_me = (
                conn.execute(
                    "SELECT 1 FROM blocks WHERE blocker_id = ? AND blocked_id = ?",
                    (int(current_user.id), profile_user["id"]),
                ).fetchone()
                is not None
            )
            return render_template(
                "social/blocked_profile.html",
                profile_user=profile_user,
                blocked_by_me=blocked_by_me,
            )

        if not profile_user["is_public"] and not is_own_profile:
            return render_template(
                "social/private_profile.html", profile_user=profile_user
            )

        status_filter = request.args.get("status", "all")
        if status_filter not in VALID_STATUSES:
            status_filter = "all"
        search_query = request.args.get("q", "").strip()
        sort_key = request.args.get("sort", DEFAULT_SORT)
        if sort_key not in SORT_OPTIONS:
            sort_key = DEFAULT_SORT

        games, counts = _fetch_games(profile_user["id"], status_filter, search_query, sort_key)

        is_following = False
        if not is_own_profile:
            is_following = (
                conn.execute(
                    "SELECT 1 FROM follows WHERE follower_id = ? AND followee_id = ?",
                    (int(current_user.id), profile_user["id"]),
                ).fetchone()
                is not None
            )

        follower_count = conn.execute(
            "SELECT COUNT(*) AS c FROM follows WHERE followee_id = ?", (profile_user["id"],)
        ).fetchone()["c"]
        following_count = conn.execute(
            "SELECT COUNT(*) AS c FROM follows WHERE follower_id = ?", (profile_user["id"],)
        ).fetchone()["c"]

        return render_template(
            "social/profile.html",
            profile_user=profile_user,
            is_own_profile=is_own_profile,
            is_following=is_following,
            follower_count=follower_count,
            following_count=following_count,
            games=games,
            status_filter=status_filter,
            search_query=search_query,
            sort_key=sort_key,
            sort_options=SORT_OPTIONS,
            counts=counts,
            total=sum(counts.values()),
        )

    @app.route("/users/<username>/follow", methods=["POST"])
    @login_required
    def user_follow(username):
        conn = db.get_db()
        user_id = int(current_user.id)
        target = conn.execute(
            "SELECT id, is_public FROM users WHERE username = ?", (username,)
        ).fetchone()
        if target is None or not target["is_public"] or target["id"] == user_id:
            abort(404)
        if _is_blocked(conn, user_id, target["id"]):
            abort(404)
        conn.execute(
            "INSERT OR IGNORE INTO follows (follower_id, followee_id) VALUES (?, ?)",
            (user_id, target["id"]),
        )
        conn.commit()
        _notify(target["id"], user_id, "follow")
        return redirect(url_for("user_profile", username=username))

    @app.route("/users/<username>/block", methods=["POST"])
    @login_required
    def user_block(username):
        conn = db.get_db()
        user_id = int(current_user.id)
        target = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if target is None or target["id"] == user_id:
            abort(404)
        conn.execute(
            "INSERT OR IGNORE INTO blocks (blocker_id, blocked_id) VALUES (?, ?)",
            (user_id, target["id"]),
        )
        conn.execute(
            """DELETE FROM follows
               WHERE (follower_id = ? AND followee_id = ?)
                  OR (follower_id = ? AND followee_id = ?)""",
            (user_id, target["id"], target["id"], user_id),
        )
        conn.commit()
        return redirect(url_for("user_directory"))

    @app.route("/users/<username>/unblock", methods=["POST"])
    @login_required
    def user_unblock(username):
        conn = db.get_db()
        target = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if target is None:
            abort(404)
        conn.execute(
            "DELETE FROM blocks WHERE blocker_id = ? AND blocked_id = ?",
            (int(current_user.id), target["id"]),
        )
        conn.commit()
        return redirect(url_for("settings"))

    @app.route("/users/<username>/unfollow", methods=["POST"])
    @login_required
    def user_unfollow(username):
        conn = db.get_db()
        target = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if target is None:
            abort(404)
        conn.execute(
            "DELETE FROM follows WHERE follower_id = ? AND followee_id = ?",
            (int(current_user.id), target["id"]),
        )
        conn.commit()
        return redirect(url_for("user_profile", username=username))

    @app.route("/feed")
    @login_required
    def feed():
        conn = db.get_db()
        user_id = int(current_user.id)
        activities = conn.execute(
            """SELECT a.*, g.title AS game_title, g.cover_url AS game_cover_url,
                      u.username AS actor_username, u.avatar_url AS actor_avatar_url,
                      (SELECT COUNT(*) FROM activity_likes al WHERE al.activity_id = a.id) AS like_count,
                      EXISTS(
                          SELECT 1 FROM activity_likes al2
                          WHERE al2.activity_id = a.id AND al2.user_id = ?
                      ) AS liked_by_me
               FROM activities a
               JOIN games g ON g.id = a.game_id
               JOIN users u ON u.id = a.user_id
               WHERE a.user_id = ?
                  OR a.user_id IN (SELECT followee_id FROM follows WHERE follower_id = ?)
               ORDER BY a.created_at DESC, a.id DESC
               LIMIT 50""",
            (user_id, user_id, user_id),
        ).fetchall()

        activity_ids = [a["id"] for a in activities]
        comments_by_activity = {}
        if activity_ids:
            placeholders = ",".join("?" for _ in activity_ids)
            comment_rows = conn.execute(
                f"""SELECT c.*, u.username FROM activity_comments c
                    JOIN users u ON u.id = c.user_id
                    WHERE c.activity_id IN ({placeholders})
                    ORDER BY c.created_at ASC, c.id ASC""",
                activity_ids,
            ).fetchall()
            for row in comment_rows:
                comments_by_activity.setdefault(row["activity_id"], []).append(row)

        return render_template(
            "social/feed.html",
            activities=activities,
            comments_by_activity=comments_by_activity,
        )

    @app.route("/feed/<int:activity_id>/like", methods=["POST"])
    @login_required
    def activity_like_toggle(activity_id):
        conn = db.get_db()
        user_id = int(current_user.id)
        if not _activity_visible(conn, activity_id, user_id):
            abort(404)

        existing = conn.execute(
            "SELECT id FROM activity_likes WHERE activity_id = ? AND user_id = ?",
            (activity_id, user_id),
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM activity_likes WHERE id = ?", (existing["id"],))
            conn.commit()
        else:
            conn.execute(
                "INSERT INTO activity_likes (activity_id, user_id) VALUES (?, ?)",
                (activity_id, user_id),
            )
            conn.commit()
            activity_owner_id = conn.execute(
                "SELECT user_id FROM activities WHERE id = ?", (activity_id,)
            ).fetchone()["user_id"]
            _notify(activity_owner_id, user_id, "like", activity_id)
        return redirect(url_for("feed"))

    @app.route("/feed/<int:activity_id>/comments", methods=["POST"])
    @login_required
    def activity_comment_add(activity_id):
        conn = db.get_db()
        user_id = int(current_user.id)
        if not _activity_visible(conn, activity_id, user_id):
            abort(404)

        body = request.form.get("body", "").strip()
        if not body:
            flash("コメントを入力してね。")
        elif len(body) > 500:
            flash("コメントは500文字以内にしてね。")
        else:
            conn.execute(
                "INSERT INTO activity_comments (activity_id, user_id, body) VALUES (?, ?, ?)",
                (activity_id, user_id, body),
            )
            conn.commit()
            activity_owner_id = conn.execute(
                "SELECT user_id FROM activities WHERE id = ?", (activity_id,)
            ).fetchone()["user_id"]
            _notify(activity_owner_id, user_id, "comment", activity_id)
        return redirect(url_for("feed"))

    @app.route("/feed/<int:activity_id>/comments/<int:comment_id>/delete", methods=["POST"])
    @login_required
    def activity_comment_delete(activity_id, comment_id):
        conn = db.get_db()
        conn.execute(
            "DELETE FROM activity_comments WHERE id = ? AND activity_id = ? AND user_id = ?",
            (comment_id, activity_id, int(current_user.id)),
        )
        conn.commit()
        return redirect(url_for("feed"))

    @app.route("/notifications")
    @login_required
    def notifications():
        conn = db.get_db()
        user_id = int(current_user.id)
        rows = conn.execute(
            """SELECT n.*, u.username AS actor_username, u.avatar_url AS actor_avatar_url,
                      g.title AS game_title
               FROM notifications n
               JOIN users u ON u.id = n.actor_id
               LEFT JOIN activities a ON a.id = n.activity_id
               LEFT JOIN games g ON g.id = a.game_id
               WHERE n.user_id = ?
               ORDER BY n.created_at DESC, n.id DESC
               LIMIT 50""",
            (user_id,),
        ).fetchall()
        conn.execute(
            "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0",
            (user_id,),
        )
        conn.commit()
        return render_template("social/notifications.html", notifications=rows)

    @app.route("/u/<token>")
    def public_list(token):
        conn = db.get_db()
        owner = conn.execute(
            "SELECT id, username FROM users WHERE share_token = ?", (token,)
        ).fetchone()
        if owner is None:
            abort(404)

        status_filter = request.args.get("status", "all")
        if status_filter not in VALID_STATUSES:
            status_filter = "all"

        search_query = request.args.get("q", "").strip()

        sort_key = request.args.get("sort", DEFAULT_SORT)
        if sort_key not in SORT_OPTIONS:
            sort_key = DEFAULT_SORT

        games, counts = _fetch_games(owner["id"], status_filter, search_query, sort_key)

        return render_template(
            "games/public_list.html",
            owner=owner,
            token=token,
            games=games,
            status_filter=status_filter,
            search_query=search_query,
            sort_key=sort_key,
            sort_options=SORT_OPTIONS,
            counts=counts,
            total=sum(counts.values()),
        )

    @app.route("/api/games/search")
    @login_required
    def api_game_search():
        query = request.args.get("q", "").strip()
        if not RAWG_API_KEY or len(query) < 2:
            return jsonify([])

        try:
            resp = requests.get(
                RAWG_SEARCH_URL,
                params={"key": RAWG_API_KEY, "search": query, "page_size": 6},
                timeout=5,
            )
            resp.raise_for_status()
        except requests.RequestException:
            return jsonify([])

        results = [
            {"name": item.get("name", ""), "cover_url": item.get("background_image")}
            for item in resp.json().get("results", [])
            if item.get("name")
        ]
        return jsonify(results)

    @app.route("/games/new", methods=["GET", "POST"])
    @login_required
    def game_new():
        if request.method == "POST":
            error = _save_game(is_new=True)
            if error is None:
                return redirect(url_for("game_list"))
            flash(error)
            return render_template("games/form.html", game=request.form, mode="new")

        return render_template("games/form.html", game={}, mode="new")

    @app.route("/games/<int:game_id>/edit", methods=["GET", "POST"])
    @login_required
    def game_edit(game_id):
        conn = db.get_db()
        game = conn.execute(
            "SELECT * FROM games WHERE id = ? AND user_id = ?",
            (game_id, int(current_user.id)),
        ).fetchone()
        if game is None:
            abort(404)

        if request.method == "POST":
            error = _save_game(is_new=False, game_id=game_id)
            if error is None:
                return redirect(url_for("game_list"))
            flash(error)
            return render_template(
                "games/form.html", game=request.form, mode="edit", game_id=game_id
            )

        return render_template("games/form.html", game=game, mode="edit", game_id=game_id)

    @app.route("/games/<int:game_id>/delete", methods=["POST"])
    @login_required
    def game_delete(game_id):
        conn = db.get_db()
        conn.execute(
            "DELETE FROM games WHERE id = ? AND user_id = ?",
            (game_id, int(current_user.id)),
        )
        conn.commit()
        return redirect(url_for("game_list"))

    @app.route("/games/<int:game_id>/sessions", methods=["GET", "POST"])
    @login_required
    def session_list(game_id):
        conn = db.get_db()
        game = conn.execute(
            "SELECT * FROM games WHERE id = ? AND user_id = ?",
            (game_id, int(current_user.id)),
        ).fetchone()
        if game is None:
            abort(404)

        if request.method == "POST":
            error = _save_session(game_id)
            if error is not None:
                flash(error)
            return redirect(url_for("session_list", game_id=game_id))

        sessions = conn.execute(
            "SELECT * FROM play_sessions WHERE game_id = ? ORDER BY played_on DESC, id DESC",
            (game_id,),
        ).fetchall()
        total_minutes = sum(s["minutes"] for s in sessions)

        return render_template(
            "games/sessions.html",
            game=game,
            sessions=sessions,
            total_minutes=total_minutes,
            today=datetime.date.today().isoformat(),
        )

    @app.route("/games/<int:game_id>/sessions/<int:session_id>/delete", methods=["POST"])
    @login_required
    def session_delete(game_id, session_id):
        conn = db.get_db()
        owned_game = conn.execute(
            "SELECT id FROM games WHERE id = ? AND user_id = ?",
            (game_id, int(current_user.id)),
        ).fetchone()
        if owned_game is None:
            abort(404)
        conn.execute(
            "DELETE FROM play_sessions WHERE id = ? AND game_id = ?", (session_id, game_id)
        )
        conn.commit()
        return redirect(url_for("session_list", game_id=game_id))

    return app


def _save_game(is_new, game_id=None):
    """フォームの内容をバリデーションしてDBに保存する。エラーがあればメッセージを返す"""
    title = request.form.get("title", "").strip()
    status = request.form.get("status", "")
    rating_raw = request.form.get("rating", "").strip()
    memo = request.form.get("memo", "").strip()
    cover_url = request.form.get("cover_url", "").strip() or None

    if not title:
        return "タイトルは必須だよ。"
    if status not in VALID_STATUSES:
        return "ステータスの値が不正だよ。"

    rating = None
    if rating_raw:
        try:
            rating = int(rating_raw)
        except ValueError:
            return "評価は数字で入力してね。"
        if not (1 <= rating <= 5):
            return "評価は1〜5の範囲で入力してね。"

    if cover_url and not (cover_url.startswith("http://") or cover_url.startswith("https://")):
        return "カバー画像のURLが不正だよ。"

    conn = db.get_db()
    user_id = int(current_user.id)

    if is_new:
        cur = conn.execute(
            "INSERT INTO games (title, status, rating, memo, cover_url, user_id) VALUES (?, ?, ?, ?, ?, ?)",
            (title, status, rating, memo, cover_url, user_id),
        )
        conn.commit()
        new_game_id = cur.lastrowid
        _log_activity(user_id, new_game_id, "added")
        if rating is not None:
            _log_activity(user_id, new_game_id, "rated", rating)
    else:
        old = conn.execute(
            "SELECT status, rating FROM games WHERE id = ? AND user_id = ?", (game_id, user_id)
        ).fetchone()
        conn.execute(
            """UPDATE games
               SET title = ?, status = ?, rating = ?, memo = ?, cover_url = ?, updated_at = datetime('now', 'localtime')
               WHERE id = ? AND user_id = ?""",
            (title, status, rating, memo, cover_url, game_id, user_id),
        )
        conn.commit()
        if old is not None:
            if old["status"] != "completed" and status == "completed":
                _log_activity(user_id, game_id, "completed")
            if rating is not None and rating != old["rating"]:
                _log_activity(user_id, game_id, "rated", rating)
    return None


def _activity_visible(conn, activity_id, viewer_id):
    """そのアクティビティが閲覧者のフィードに表示される対象か(自分のか、フォロー中のユーザーのものか)"""
    row = conn.execute(
        """SELECT 1 FROM activities a
           WHERE a.id = ? AND (
               a.user_id = ? OR a.user_id IN (SELECT followee_id FROM follows WHERE follower_id = ?)
           )""",
        (activity_id, viewer_id, viewer_id),
    ).fetchone()
    return row is not None


def _log_activity(user_id, game_id, kind, rating=None):
    conn = db.get_db()
    conn.execute(
        "INSERT INTO activities (user_id, game_id, kind, rating) VALUES (?, ?, ?, ?)",
        (user_id, game_id, kind, rating),
    )
    conn.commit()


def _is_blocked(conn, user_a, user_b):
    """user_aとuser_bのどちらかがもう片方をブロックしているか"""
    row = conn.execute(
        """SELECT 1 FROM blocks
           WHERE (blocker_id = ? AND blocked_id = ?) OR (blocker_id = ? AND blocked_id = ?)""",
        (user_a, user_b, user_b, user_a),
    ).fetchone()
    return row is not None


def _notify(recipient_id, actor_id, kind, activity_id=None):
    """自分自身の行動には通知を出さない"""
    if recipient_id == actor_id:
        return
    conn = db.get_db()
    conn.execute(
        "INSERT INTO notifications (user_id, actor_id, kind, activity_id) VALUES (?, ?, ?, ?)",
        (recipient_id, actor_id, kind, activity_id),
    )
    conn.commit()


def _save_session(game_id):
    """プレイセッションのフォームをバリデーションしてDBに保存する。エラーがあればメッセージを返す"""
    played_on = request.form.get("played_on", "").strip()
    hours_raw = request.form.get("hours", "").strip()
    minutes_raw = request.form.get("minutes", "").strip()

    if not played_on:
        return "日付は必須だよ。"
    try:
        datetime.date.fromisoformat(played_on)
    except ValueError:
        return "日付の形式が正しくないよ。"

    try:
        hours = int(hours_raw) if hours_raw else 0
        minutes = int(minutes_raw) if minutes_raw else 0
    except ValueError:
        return "プレイ時間は数字で入力してね。"

    if hours < 0 or minutes < 0:
        return "プレイ時間は0以上で入力してね。"

    total_minutes = hours * 60 + minutes
    if total_minutes <= 0:
        return "プレイ時間を入力してね。"

    conn = db.get_db()
    conn.execute(
        "INSERT INTO play_sessions (game_id, played_on, minutes) VALUES (?, ?, ?)",
        (game_id, played_on, total_minutes),
    )
    conn.commit()
    return None


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
