"""KENFLO EMOTIONAL HEALTH SERVICE LLC - configuration."""
import os
import secrets
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # In production ALWAYS set KENFLO_SECRET_KEY in the environment / systemd unit.
    SECRET_KEY = os.environ.get("KENFLO_SECRET_KEY") or secrets.token_hex(32)

    # SQLite by default; point DATABASE_URL at PostgreSQL in production, e.g.
    #   postgresql+psycopg://kenflo:pass@localhost/kenflo
    _db_url = os.environ.get("DATABASE_URL")
    if not _db_url:
        _db_path = Path(os.environ.get("KENFLO_DB_DIR", BASE_DIR / "instance"))
        _db_path.mkdir(parents=True, exist_ok=True)
        _db_url = f"sqlite:///{_db_path / 'kenflo.db'}"
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session / cookie hardening. Set KENFLO_COOKIE_SECURE=1 once the site is HTTPS.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("KENFLO_COOKIE_SECURE")
    SESSION_COOKIE_NAME = "kenflo_session"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # 1 MiB request cap

    # Business facts surfaced in templates / SEO.
    SITE_NAME = "KENFLO Emotional Health Services LLC"
    SITE_TAGLINE = "Strengthening Emotional Wellness. Building Resilience. Supporting Healthier Lives and Communities."
    SEO_TITLE = "KENFLO Emotional Health Services | Emotional Wellness & Resilience Support in Minnesota"
    SEO_DESCRIPTION = (
        "KENFLO Emotional Health Services LLC provides non-clinical emotional wellness support, "
        "coaching, family and youth programs, cultural adjustment support, workshops, and "
        "organizational wellness services in Minnesota."
    )
