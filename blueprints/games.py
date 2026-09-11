import csv
import datetime
import io

import requests
from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

import core
import db

bp = Blueprint("games", __name__)


@bp.route("/games")
@login_required
def game_list():
    status_filter = request.args.get("status", "all")
    if status_filter not in core.VALID_STATUSES:
        status_filter = "all"

    search_query = request.args.get("q", "").strip()

    sort_key = request.args.get("sort", core.DEFAULT_SORT)
    if sort_key not in core.SORT_OPTIONS:
        sort_key = core.DEFAULT_SORT

    favorite_only = request.args.get("favorite") == "1"

    games, counts = core.fetch_games(
        int(current_user.id), status_filter, search_query, sort_key, favorite_only
    )

    return render_template(
        "games/list.html",
        games=games,
        status_filter=status_filter,
        search_query=search_query,
        sort_key=sort_key,
        sort_options=core.SORT_OPTIONS,
        counts=counts,
        total=sum(counts.values()),
        favorite_only=favorite_only,
    )


@bp.route("/games/<int:game_id>/favorite/toggle", methods=["POST"])
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
            "games.game_list",
            status=request.form.get("status") or None,
            q=request.form.get("q") or None,
            sort=request.form.get("sort") or None,
            favorite=request.form.get("favorite") or None,
        )
    )


@bp.route("/api/games/search")
@login_required
def api_game_search():
    query = request.args.get("q", "").strip()
    if not core.RAWG_API_KEY or len(query) < 2:
        return jsonify([])

    try:
        resp = requests.get(
            core.RAWG_SEARCH_URL,
            params={"key": core.RAWG_API_KEY, "search": query, "page_size": 6},
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


@bp.route("/games/new", methods=["GET", "POST"])
@login_required
def game_new():
    if request.method == "POST":
        error = core.save_game(is_new=True)
        if error is None:
            return redirect(url_for("games.game_list"))
        flash(error)
        return render_template("games/form.html", game=request.form, mode="new")

    return render_template("games/form.html", game={}, mode="new")


@bp.route("/games/<int:game_id>/edit", methods=["GET", "POST"])
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
        error = core.save_game(is_new=False, game_id=game_id)
        if error is None:
            return redirect(url_for("games.game_list"))
        flash(error)
        return render_template(
            "games/form.html", game=request.form, mode="edit", game_id=game_id
        )

    return render_template("games/form.html", game=game, mode="edit", game_id=game_id)


@bp.route("/games/<int:game_id>/delete", methods=["POST"])
@login_required
def game_delete(game_id):
    conn = db.get_db()
    conn.execute(
        "DELETE FROM games WHERE id = ? AND user_id = ?",
        (game_id, int(current_user.id)),
    )
    conn.commit()
    return redirect(url_for("games.game_list"))


@bp.route("/games/<int:game_id>/sessions", methods=["GET", "POST"])
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
        error = core.save_session(game_id)
        if error is not None:
            flash(error)
        return redirect(url_for("games.session_list", game_id=game_id))

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


@bp.route("/games/<int:game_id>/sessions/<int:session_id>/delete", methods=["POST"])
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
    return redirect(url_for("games.session_list", game_id=game_id))


@bp.route("/export/games.csv")
@login_required
def export_games_csv():
    conn = db.get_db()
    rows = conn.execute(
        """SELECT g.title, g.status, g.rating, g.memo, g.cover_url, g.is_favorite,
                  g.created_at, g.updated_at, COALESCE(SUM(ps.minutes), 0) AS total_minutes
           FROM games g
           LEFT JOIN play_sessions ps ON ps.game_id = g.id
           WHERE g.user_id = ?
           GROUP BY g.id
           ORDER BY g.title COLLATE NOCASE ASC""",
        (int(current_user.id),),
    ).fetchall()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "title",
            "status",
            "rating",
            "memo",
            "cover_url",
            "is_favorite",
            "created_at",
            "updated_at",
            "total_minutes",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["title"],
                core.STATUS_LABELS.get(row["status"], row["status"]),
                row["rating"] or "",
                row["memo"] or "",
                row["cover_url"] or "",
                "yes" if row["is_favorite"] else "no",
                row["created_at"],
                row["updated_at"],
                row["total_minutes"],
            ]
        )

    # Excelで開いたときに文字化けしないよう、UTF-8のBOMを先頭に付ける
    csv_text = "﻿" + buffer.getvalue()

    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=games.csv"},
    )
