import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

import db
from auth import User

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,20}$")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("games.game_list"))

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
            conn.execute("UPDATE games SET user_id = ? WHERE user_id IS NULL", (new_user_id,))
            conn.commit()

        login_user(User(new_user_id, username))
        return redirect(url_for("games.game_list"))

    return render_template("auth/register.html", username=username)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("games.game_list"))

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
        return redirect(next_url or url_for("games.game_list"))

    return render_template("auth/login.html", username=username)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
