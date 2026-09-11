"""ゲーム本体・プレイセッションに関するDBアクセスヘルパー。"""

import datetime

from flask import request
from flask_login import current_user

import db

from .constants import MEMO_MAX_LENGTH, SORT_OPTIONS, VALID_STATUSES
from .social import log_activity


def fetch_games(user_id, status_filter, search_query, sort_key, favorite_only=False):
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


def save_game(is_new, game_id=None):
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
    if len(memo) > MEMO_MAX_LENGTH:
        return f"メモは{MEMO_MAX_LENGTH}文字以内にしてね。"

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
        log_activity(user_id, new_game_id, "added")
        if rating is not None:
            log_activity(user_id, new_game_id, "rated", rating)
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
                log_activity(user_id, game_id, "completed")
            if rating is not None and rating != old["rating"]:
                log_activity(user_id, game_id, "rated", rating)
    return None


def save_session(game_id):
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
