"""アクティビティ・通知・ブロックに関するDBアクセスヘルパー。"""

import db


def log_activity(user_id, game_id, kind, rating=None):
    conn = db.get_db()
    conn.execute(
        "INSERT INTO activities (user_id, game_id, kind, rating) VALUES (?, ?, ?, ?)",
        (user_id, game_id, kind, rating),
    )
    conn.commit()


def activity_visible(conn, activity_id, viewer_id):
    """そのアクティビティが閲覧者のフィードに表示される対象か(自分のか、フォロー中のユーザーのものか)"""
    row = conn.execute(
        """SELECT 1 FROM activities a
           WHERE a.id = ? AND (
               a.user_id = ? OR a.user_id IN (SELECT followee_id FROM follows WHERE follower_id = ?)
           )""",
        (activity_id, viewer_id, viewer_id),
    ).fetchone()
    return row is not None


def is_blocked(conn, user_a, user_b):
    """user_aとuser_bのどちらかがもう片方をブロックしているか"""
    row = conn.execute(
        """SELECT 1 FROM blocks
           WHERE (blocker_id = ? AND blocked_id = ?) OR (blocker_id = ? AND blocked_id = ?)""",
        (user_a, user_b, user_b, user_a),
    ).fetchone()
    return row is not None


def notify(recipient_id, actor_id, kind, activity_id=None):
    """自分自身の行動には通知を出さない"""
    if recipient_id == actor_id:
        return
    conn = db.get_db()
    conn.execute(
        "INSERT INTO notifications (user_id, actor_id, kind, activity_id) VALUES (?, ?, ?, ?)",
        (recipient_id, actor_id, kind, activity_id),
    )
    conn.commit()
