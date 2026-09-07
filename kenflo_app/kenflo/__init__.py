"""KENFLO Emotional Health Services LLC — application factory."""
from flask import Flask, render_template

from .config import Config
from .models import db


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    from .public import bp as public_bp
    from .admin import bp as admin_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # Template globals / filters -------------------------------------------
    from .security import csrf_token

    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["site_name"] = app.config["SITE_NAME"]
    app.jinja_env.globals["site_tagline"] = app.config["SITE_TAGLINE"]

    from .models import CLIENT_STATUSES, PREFERRED_CONTACT, REQUEST_CATEGORIES, REQUEST_PRIORITIES, REQUEST_STATUSES

    def labels(pairs):
        return {k: v for k, v in pairs}

    app.jinja_env.globals["REQ_CATEGORIES"] = labels(REQUEST_CATEGORIES)
    app.jinja_env.globals["REQ_STATUSES"] = labels(REQUEST_STATUSES)
    app.jinja_env.globals["REQ_PRIORITIES"] = labels(REQUEST_PRIORITIES)
    app.jinja_env.globals["CLIENT_STATUSES"] = labels(CLIENT_STATUSES)
    app.jinja_env.globals["PREFERRED_CONTACT"] = labels(PREFERRED_CONTACT)

    @app.context_processor
    def _inject_globals():
        from datetime import datetime, timezone

        from .security import current_user

        return {
            "current_year": datetime.now(timezone.utc).year,
            "cur_user": current_user(),
        }

    # Error handlers --------------------------------------------------------
    def _error(code, title, message):
        return render_template("errors.html", code=code, title=title, message=message), code

    @app.errorhandler(400)
    def e400(err):
        return _error(400, "Bad request", getattr(err, "description", "The request could not be processed."))

    @app.errorhandler(403)
    def e403(_err):
        return _error(403, "Not allowed", "You do not have permission to perform that action.")

    @app.errorhandler(404)
    def e404(_err):
        return _error(404, "Page not found", "The page you are looking for does not exist or has moved.")

    @app.errorhandler(500)
    def e500(_err):
        return _error(500, "Something went wrong", "An unexpected error occurred. Please try again later.")

    with app.app_context():
        db.create_all()

    # CLI --------------------------------------------------------------------
    @app.cli.command("seed-admin")
    def seed_admin():
        """Create (or reset the password of) the initial administrator.

        Usage:
          KENFLO_ADMIN_EMAIL=you@example.org KENFLO_ADMIN_PASSWORD='long-password' flask seed-admin
        """
        import os

        from .models import StaffUser

        email = (os.environ.get("KENFLO_ADMIN_EMAIL") or "admin@kenflo.org").strip().lower()
        password = os.environ.get("KENFLO_ADMIN_PASSWORD") or ""
        name = os.environ.get("KENFLO_ADMIN_NAME") or "KENFLO Admin"
        if len(password) < 10:
            raise SystemExit("Set KENFLO_ADMIN_PASSWORD to at least 10 characters.")
        user = db.session.query(StaffUser).filter_by(email=email).first()
        if user is None:
            user = StaffUser(name=name, email=email, role="admin")
            user.set_password(password)
            db.session.add(user)
            action = "created"
        else:
            user.set_password(password)
            user.is_active = True
            user.role = "admin"
            action = "password reset for"
        db.session.commit()
        print(f"Admin account {action}: {email}")

    return app
