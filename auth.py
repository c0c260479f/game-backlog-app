from flask_login import LoginManager, UserMixin

import db

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "ログインしてね。"


class User(UserMixin):
    def __init__(self, id, username, avatar_url=None):
        self.id = str(id)
        self.username = username
        self.avatar_url = avatar_url

    @staticmethod
    def get(user_id):
        conn = db.get_db()
        row = conn.execute(
            "SELECT id, username, avatar_url FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return User(row["id"], row["username"], row["avatar_url"])


@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)


def init_app(app):
    login_manager.init_app(app)
