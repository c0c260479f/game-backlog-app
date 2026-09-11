import sqlite3
from pathlib import Path

import click
from flask import current_app, g

DB_PATH = Path(__file__).parent / "games.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_db():
    """リクエストごとに1つのDB接続を使い回す"""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """schema.sql を実行してテーブルを作り直す"""
    db = get_db()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()


@click.command("init-db")
def init_db_command():
    """`flask init-db` で呼べるコマンド。DBを初期化(既存データは消える)する"""
    init_db()
    click.echo("データベースを初期化しました。")


def ensure_play_sessions_table():
    """既存のgames.dbにplay_sessionsテーブルがなければ追加する(既存データは消さない)"""
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS play_sessions (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               game_id INTEGER NOT NULL REFERENCES games (id) ON DELETE CASCADE,
               played_on TEXT NOT NULL,
               minutes INTEGER NOT NULL CHECK (minutes > 0),
               created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_play_sessions_game_id ON play_sessions (game_id)"
    )
    conn.commit()


def ensure_cover_url_column():
    """既存のgamesテーブルにcover_url列がなければ追加する(既存データは消さない)"""
    conn = get_db()
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(games)").fetchall()]
    if "cover_url" not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN cover_url TEXT")
        conn.commit()


def ensure_users_table():
    """usersテーブルがなければ追加する(既存データは消さない)"""
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               username TEXT NOT NULL UNIQUE,
               password_hash TEXT NOT NULL,
               created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
           )"""
    )
    conn.commit()


def ensure_user_id_column():
    """既存のgamesテーブルにuser_id列がなければ追加する(既存データは消さない)"""
    conn = get_db()
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(games)").fetchall()]
    if "user_id" not in columns:
        conn.execute(
            "ALTER TABLE games ADD COLUMN user_id INTEGER REFERENCES users (id) ON DELETE CASCADE"
        )
        conn.commit()
    conn.execute("CREATE INDEX IF NOT EXISTS idx_games_user_id ON games (user_id)")
    conn.commit()


def ensure_share_token_column():
    """既存のusersテーブルにshare_token列がなければ追加する(既存データは消さない)"""
    conn = get_db()
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "share_token" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN share_token TEXT")
        conn.commit()
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_users_share_token
           ON users (share_token) WHERE share_token IS NOT NULL"""
    )
    conn.commit()


def ensure_is_public_column():
    """既存のusersテーブルにis_public列がなければ追加する(既存データは消さない)"""
    conn = get_db()
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "is_public" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0")
        conn.commit()


def ensure_follows_table():
    """followsテーブルがなければ追加する(既存データは消さない)"""
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS follows (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               follower_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
               followee_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
               created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
               CHECK (follower_id != followee_id),
               UNIQUE (follower_id, followee_id)
           )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_follows_follower ON follows (follower_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_follows_followee ON follows (followee_id)")
    conn.commit()


def ensure_activities_tables():
    """activities・activity_likes・activity_commentsテーブルがなければ追加する(既存データは消さない)"""
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS activities (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
               game_id INTEGER NOT NULL REFERENCES games (id) ON DELETE CASCADE,
               kind TEXT NOT NULL CHECK (kind IN ('added', 'completed', 'rated')),
               rating INTEGER,
               created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
           )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_user_id ON activities (user_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_activities_created_at ON activities (created_at)"
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS activity_likes (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               activity_id INTEGER NOT NULL REFERENCES activities (id) ON DELETE CASCADE,
               user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
               created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
               UNIQUE (activity_id, user_id)
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_likes_activity_id ON activity_likes (activity_id)"
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS activity_comments (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               activity_id INTEGER NOT NULL REFERENCES activities (id) ON DELETE CASCADE,
               user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
               body TEXT NOT NULL,
               created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
           )"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_activity_comments_activity_id
           ON activity_comments (activity_id)"""
    )
    conn.commit()


def ensure_avatar_url_column():
    """既存のusersテーブルにavatar_url列がなければ追加する(既存データは消さない)"""
    conn = get_db()
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "avatar_url" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
        conn.commit()


def ensure_is_favorite_column():
    """既存のgamesテーブルにis_favorite列がなければ追加する(既存データは消さない)"""
    conn = get_db()
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(games)").fetchall()]
    if "is_favorite" not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")
        conn.commit()


def ensure_blocks_table():
    """blocksテーブルがなければ追加する(既存データは消さない)"""
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS blocks (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               blocker_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
               blocked_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
               created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
               CHECK (blocker_id != blocked_id),
               UNIQUE (blocker_id, blocked_id)
           )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_blocks_blocker ON blocks (blocker_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_blocks_blocked ON blocks (blocked_id)")
    conn.commit()


def ensure_notifications_table():
    """notificationsテーブルがなければ追加する(既存データは消さない)"""
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS notifications (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
               actor_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
               kind TEXT NOT NULL CHECK (kind IN ('follow', 'like', 'comment')),
               activity_id INTEGER REFERENCES activities (id) ON DELETE CASCADE,
               is_read INTEGER NOT NULL DEFAULT 0,
               created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications (user_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications (created_at)"
    )
    conn.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    with app.app_context():
        ensure_play_sessions_table()
        ensure_cover_url_column()
        ensure_users_table()
        ensure_user_id_column()
        ensure_share_token_column()
        ensure_is_public_column()
        ensure_follows_table()
        ensure_activities_tables()
        ensure_avatar_url_column()
        ensure_is_favorite_column()
        ensure_blocks_table()
        ensure_notifications_table()
