"""KENFLO database models."""
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


REQUEST_CATEGORIES = [
    ("support", "Individual / Family Support"),
    ("workshop", "Workshop Request"),
    ("school", "School Partnership"),
    ("organization", "Organizational / Community Partnership"),
    ("cultural", "Cultural & Immigration Support"),
    ("general", "General Inquiry"),
]

REQUEST_STATUSES = [
    ("new", "New"),
    ("in_review", "In Review"),
    ("contacted", "Contacted"),
    ("scheduled", "Scheduled"),
    ("active", "Active"),
    ("completed", "Completed"),
    ("closed", "Closed"),
    ("declined", "Declined / Referred Out"),
]

REQUEST_PRIORITIES = [
    ("low", "Low"),
    ("normal", "Normal"),
    ("high", "High"),
    ("urgent", "Urgent"),
]

CLIENT_STATUSES = [
    ("active", "Active"),
    ("inactive", "Inactive"),
    ("archived", "Archived"),
]

PREFERRED_CONTACT = [
    ("email", "Email"),
    ("phone", "Phone call"),
    ("text", "Text message"),
]


class StaffUser(db.Model):
    __tablename__ = "staff_users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="staff")  # admin | staff
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    assigned_requests = db.relationship(
        "ServiceRequest", back_populates="assigned_to", foreign_keys="ServiceRequest.assigned_to_id"
    )
    notes = db.relationship("Note", back_populates="author")

    def set_password(self, raw: str) -> None:
        from werkzeug.security import generate_password_hash

        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        from werkzeug.security import check_password_hash

        return check_password_hash(self.password_hash, raw)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StaffUser {self.email} ({self.role})>"


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), index=True)
    phone = db.Column(db.String(40))
    preferred_contact = db.Column(db.String(20), nullable=False, default="email")
    city = db.Column(db.String(120))
    language = db.Column(db.String(80))
    age_group = db.Column(db.String(40))
    referred_by = db.Column(db.String(200))
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    requests = db.relationship("ServiceRequest", back_populates="client")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Client {self.full_name}>"


class ServiceRequest(db.Model):
    """An inbound inquiry from the website OR a manually created (office) request."""

    __tablename__ = "service_requests"

    id = db.Column(db.Integer, primary_key=True)
    reference_code = db.Column(db.String(16), unique=True, nullable=False, index=True)
    category = db.Column(db.String(30), nullable=False, default="support", index=True)
    service_interest = db.Column(db.String(200))
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(255), index=True)
    phone = db.Column(db.String(40))
    preferred_contact = db.Column(db.String(20), nullable=False, default="email")
    organization = db.Column(db.String(200))
    city = db.Column(db.String(120))
    message = db.Column(db.Text, nullable=False)
    preferred_time = db.Column(db.String(120))
    status = db.Column(db.String(20), nullable=False, default="new", index=True)
    priority = db.Column(db.String(20), nullable=False, default="normal", index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"))
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("staff_users.id"))
    admin_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    client = db.relationship("Client", back_populates="requests")
    assigned_to = db.relationship("StaffUser", back_populates="assigned_requests", foreign_keys=[assigned_to_id])
    notes = db.relationship(
        "Note", back_populates="request", cascade="all, delete-orphan", order_by="Note.created_at.desc()"
    )

    @property
    def source(self) -> str:
        return "Website" if self.reference_code.startswith("KF-W") else "Office"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ServiceRequest {self.reference_code} ({self.status})>"


class Note(db.Model):
    """Activity / follow-up log attached to a service request."""

    __tablename__ = "notes"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("service_requests.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("staff_users.id"))
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    request = db.relationship("ServiceRequest", back_populates="notes")
    author = db.relationship("StaffUser", back_populates="notes")


def new_reference_code(prefix: str = "KF-W") -> str:
    """Human-friendly reference like KF-W-7Q2M4D (website) / KF-O-9XK2BT (office).

    Ambiguous characters (0/O, 1/I/L) are excluded.
    """
    import secrets

    alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    body = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"{prefix}-{body}"
