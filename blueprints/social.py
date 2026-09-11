from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

import core
import db

bp = Blueprint("social", __name__)


@bp.route("/settings")
@login_required
def settings():
    conn = db.get_db()
    user_row = conn.execute(
        "SELECT username, share_token, is_public, avatar_url FROM users WHERE id = ?",
        (int(current_user.id),),
    ).fetchone()
    share_url = (
        url_for("sharing.public_list", token=user_row["share_token"], _external=True)
        if user_row["share_token"]
        else None
    )
    profile_url = (
        url_for("social.user_profile", username=user_row["username"], _external=True)
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


@bp.route("/profile/avatar", methods=["POST"])
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
            return redirect(url_for("social.settings"))
        new_avatar_url = game["cover_url"]
    elif avatar_url:
        if not (avatar_url.startswith("http://") or avatar_url.startswith("https://")):
            flash("画像のURLが不正だよ。")
            return redirect(url_for("social.settings"))
        new_avatar_url = avatar_url
    else:
        flash("画像URLを入力するか、お気に入りゲームを選んでね。")
        return redirect(url_for("social.settings"))

    conn.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (new_avatar_url, user_id))
    conn.commit()
    return redirect(url_for("social.settings"))


@bp.route("/profile/avatar/clear", methods=["POST"])
@login_required
def profile_avatar_clear():
    conn = db.get_db()
    conn.execute("UPDATE users SET avatar_url = NULL WHERE id = ?", (int(current_user.id),))
    conn.commit()
    return redirect(url_for("social.settings"))


@bp.route("/profile/enable", methods=["POST"])
@login_required
def profile_enable():
    conn = db.get_db()
    conn.execute("UPDATE users SET is_public = 1 WHERE id = ?", (int(current_user.id),))
    conn.commit()
    return redirect(url_for("social.settings"))


@bp.route("/profile/disable", methods=["POST"])
@login_required
def profile_disable():
    conn = db.get_db()
    conn.execute("UPDATE users SET is_public = 0 WHERE id = ?", (int(current_user.id),))
    conn.commit()
    return redirect(url_for("social.settings"))


@bp.route("/users")
@login_required
def user_directory():
    search_query = request.args.get("q", "").strip()
    sort_key = request.args.get("sort", core.DEFAULT_DIRECTORY_SORT)
    if sort_key not in core.DIRECTORY_SORT_OPTIONS:
        sort_key = core.DEFAULT_DIRECTORY_SORT

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

    order_clause = core.DIRECTORY_SORT_OPTIONS[sort_key][1]

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
        sort_options=core.DIRECTORY_SORT_OPTIONS,
    )


@bp.route("/users/<username>")
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

    if not is_own_profile and core.is_blocked(conn, int(current_user.id), profile_user["id"]):
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
        return render_template("social/private_profile.html", profile_user=profile_user)

    status_filter = request.args.get("status", "all")
    if status_filter not in core.VALID_STATUSES:
        status_filter = "all"
    search_query = request.args.get("q", "").strip()
    sort_key = request.args.get("sort", core.DEFAULT_SORT)
    if sort_key not in core.SORT_OPTIONS:
        sort_key = core.DEFAULT_SORT

    games, counts = core.fetch_games(profile_user["id"], status_filter, search_query, sort_key)

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
        sort_options=core.SORT_OPTIONS,
        counts=counts,
        total=sum(counts.values()),
    )


@bp.route("/users/<username>/follow", methods=["POST"])
@login_required
def user_follow(username):
    conn = db.get_db()
    user_id = int(current_user.id)
    target = conn.execute(
        "SELECT id, is_public FROM users WHERE username = ?", (username,)
    ).fetchone()
    if target is None or not target["is_public"] or target["id"] == user_id:
        abort(404)
    if core.is_blocked(conn, user_id, target["id"]):
        abort(404)
    conn.execute(
        "INSERT OR IGNORE INTO follows (follower_id, followee_id) VALUES (?, ?)",
        (user_id, target["id"]),
    )
    conn.commit()
    core.notify(target["id"], user_id, "follow")
    return redirect(url_for("social.user_profile", username=username))


@bp.route("/users/<username>/block", methods=["POST"])
@login_required
def user_block(username):
    conn = db.get_db()
    user_id = int(current_user.id)
    target = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
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
    return redirect(url_for("social.user_directory"))


@bp.route("/users/<username>/unblock", methods=["POST"])
@login_required
def user_unblock(username):
    conn = db.get_db()
    target = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if target is None:
        abort(404)
    conn.execute(
        "DELETE FROM blocks WHERE blocker_id = ? AND blocked_id = ?",
        (int(current_user.id), target["id"]),
    )
    conn.commit()
    return redirect(url_for("social.settings"))


@bp.route("/users/<username>/unfollow", methods=["POST"])
@login_required
def user_unfollow(username):
    conn = db.get_db()
    target = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if target is None:
        abort(404)
    conn.execute(
        "DELETE FROM follows WHERE follower_id = ? AND followee_id = ?",
        (int(current_user.id), target["id"]),
    )
    conn.commit()
    return redirect(url_for("social.user_profile", username=username))


PAGE_SIZE = 50


@bp.route("/feed")
@login_required
def feed():
    conn = db.get_db()
    user_id = int(current_user.id)

    before_id = request.args.get("before_id", type=int)
    cursor_condition = "AND a.id < ?" if before_id else ""
    cursor_params = [before_id] if before_id else []

    activities = conn.execute(
        f"""SELECT a.*, g.title AS game_title, g.cover_url AS game_cover_url,
                  u.username AS actor_username, u.avatar_url AS actor_avatar_url,
                  (SELECT COUNT(*) FROM activity_likes al WHERE al.activity_id = a.id) AS like_count,
                  EXISTS(
                      SELECT 1 FROM activity_likes al2
                      WHERE al2.activity_id = a.id AND al2.user_id = ?
                  ) AS liked_by_me
           FROM activities a
           JOIN games g ON g.id = a.game_id
           JOIN users u ON u.id = a.user_id
           WHERE (a.user_id = ?
              OR a.user_id IN (SELECT followee_id FROM follows WHERE follower_id = ?))
              {cursor_condition}
           ORDER BY a.created_at DESC, a.id DESC
           LIMIT {PAGE_SIZE + 1}""",
        [user_id, user_id, user_id, *cursor_params],
    ).fetchall()

    has_more = len(activities) > PAGE_SIZE
    activities = activities[:PAGE_SIZE]
    next_before_id = activities[-1]["id"] if has_more else None

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
        next_before_id=next_before_id,
    )


@bp.route("/feed/<int:activity_id>/like", methods=["POST"])
@login_required
def activity_like_toggle(activity_id):
    conn = db.get_db()
    user_id = int(current_user.id)
    if not core.activity_visible(conn, activity_id, user_id):
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
        core.notify(activity_owner_id, user_id, "like", activity_id)
    return redirect(url_for("social.feed"))


@bp.route("/feed/<int:activity_id>/comments", methods=["POST"])
@login_required
def activity_comment_add(activity_id):
    conn = db.get_db()
    user_id = int(current_user.id)
    if not core.activity_visible(conn, activity_id, user_id):
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
        core.notify(activity_owner_id, user_id, "comment", activity_id)
    return redirect(url_for("social.feed"))


@bp.route("/feed/<int:activity_id>/comments/<int:comment_id>/delete", methods=["POST"])
@login_required
def activity_comment_delete(activity_id, comment_id):
    conn = db.get_db()
    conn.execute(
        "DELETE FROM activity_comments WHERE id = ? AND activity_id = ? AND user_id = ?",
        (comment_id, activity_id, int(current_user.id)),
    )
    conn.commit()
    return redirect(url_for("social.feed"))


@bp.route("/notifications")
@login_required
def notifications():
    conn = db.get_db()
    user_id = int(current_user.id)

    before_id = request.args.get("before_id", type=int)
    cursor_condition = "AND n.id < ?" if before_id else ""
    cursor_params = [before_id] if before_id else []

    rows = conn.execute(
        f"""SELECT n.*, u.username AS actor_username, u.avatar_url AS actor_avatar_url,
                  g.title AS game_title
           FROM notifications n
           JOIN users u ON u.id = n.actor_id
           LEFT JOIN activities a ON a.id = n.activity_id
           LEFT JOIN games g ON g.id = a.game_id
           WHERE n.user_id = ?
              {cursor_condition}
           ORDER BY n.created_at DESC, n.id DESC
           LIMIT {PAGE_SIZE + 1}""",
        [user_id, *cursor_params],
    ).fetchall()

    has_more = len(rows) > PAGE_SIZE
    rows = rows[:PAGE_SIZE]
    next_before_id = rows[-1]["id"] if has_more else None

    conn.execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0",
        (user_id,),
    )
    conn.commit()
    return render_template(
        "social/notifications.html", notifications=rows, next_before_id=next_before_id
    )
