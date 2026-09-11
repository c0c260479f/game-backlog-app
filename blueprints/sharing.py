import secrets

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

import core
import db

bp = Blueprint("sharing", __name__)


@bp.route("/share/generate", methods=["POST"])
@login_required
def share_generate():
    conn = db.get_db()
    token = secrets.token_urlsafe(24)
    conn.execute("UPDATE users SET share_token = ? WHERE id = ?", (token, int(current_user.id)))
    conn.commit()
    return redirect(url_for("social.settings"))


@bp.route("/share/disable", methods=["POST"])
@login_required
def share_disable():
    conn = db.get_db()
    conn.execute("UPDATE users SET share_token = NULL WHERE id = ?", (int(current_user.id),))
    conn.commit()
    return redirect(url_for("social.settings"))


@bp.route("/u/<token>")
def public_list(token):
    conn = db.get_db()
    owner = conn.execute(
        "SELECT id, username FROM users WHERE share_token = ?", (token,)
    ).fetchone()
    if owner is None:
        abort(404)

    status_filter = request.args.get("status", "all")
    if status_filter not in core.VALID_STATUSES:
        status_filter = "all"

    search_query = request.args.get("q", "").strip()

    sort_key = request.args.get("sort", core.DEFAULT_SORT)
    if sort_key not in core.SORT_OPTIONS:
        sort_key = core.DEFAULT_SORT

    games, counts = core.fetch_games(owner["id"], status_filter, search_query, sort_key)

    return render_template(
        "games/public_list.html",
        owner=owner,
        token=token,
        games=games,
        status_filter=status_filter,
        search_query=search_query,
        sort_key=sort_key,
        sort_options=core.SORT_OPTIONS,
        counts=counts,
        total=sum(counts.values()),
    )
