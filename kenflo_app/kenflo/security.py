"""Authentication, CSRF, and rate-limiting helpers (no external deps)."""
import hmac
import secrets
import time
from collections import defaultdict
from functools import wraps

from flask import abort, flash, redirect, request, session, url_for

from .models import StaffUser

# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------


def csrf_token() -> str:
    """Return (lazily creating) the CSRF token for the current session."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["_csrf_token"] = token
    return token


def check_csrf() -> None:
    token = session.get("_csrf_token")
    sent = request.form.get("_csrf", "")
    if not token or not sent or not hmac.compare_digest(token, sent):
        abort(400, description="Invalid or missing CSRF token. Please go back and try again.")


# ---------------------------------------------------------------------------
# Login helpers
# ---------------------------------------------------------------------------


def current_user() -> StaffUser | None:
    uid = session.get("staff_id")
    if uid is None:
        return None
    user = db_get_user(uid)
    if user is None or not user.is_active:
        session.clear()
        return None
    return user


def db_get_user(uid: int):
    from . import db
    from .models import StaffUser as U

    return db.session.get(U, uid)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user().is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


# ---------------------------------------------------------------------------
# Brute-force protection (in-memory; resets on restart — fine for a small team)
# ---------------------------------------------------------------------------

_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 15 * 60
_attempts: dict[str, list[float]] = defaultdict(list)


def _attempt_key(email: str) -> str:
    return f"{request.remote_addr or '?'}|{email.strip().lower()}"


def register_failed_login(email: str) -> None:
    key = _attempt_key(email)
    now = time.monotonic()
    _attempts[key] = [t for t in _attempts[key] if now - t < _LOCKOUT_SECONDS]
    _attempts[key].append(now)


def clear_failed_logins(email: str) -> None:
    _attempts.pop(_attempt_key(email), None)


def is_locked_out(email: str) -> bool:
    key = _attempt_key(email)
    now = time.monotonic()
    recent = [t for t in _attempts[key] if now - t < _LOCKOUT_SECONDS]
    if len(recent) >= _MAX_ATTEMPTS:
        return True
    _attempts[key] = recent
    return False
