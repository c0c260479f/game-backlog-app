import os

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, url_for
from flask_login import current_user
from flask_wtf import CSRFProtect

import auth
import core
import db
from blueprints.auth import bp as auth_bp
from blueprints.games import bp as games_bp
from blueprints.sharing import bp as sharing_bp
from blueprints.social import bp as social_bp
from extensions import limiter

load_dotenv()


def create_app(test_config=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    auth.init_app(app)
    CSRFProtect(app)
    limiter.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(games_bp)
    app.register_blueprint(sharing_bp)
    app.register_blueprint(social_bp)

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
            "STATUS_LABELS": core.STATUS_LABELS,
            "format_minutes": core.format_minutes,
            "ACTIVITY_KIND_LABELS": core.ACTIVITY_KIND_LABELS,
            "unread_notification_count": unread_notification_count,
        }

    @app.route("/")
    def index():
        return redirect(url_for("games.game_list"))

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("errors/400.html"), 400

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def rate_limited(e):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
