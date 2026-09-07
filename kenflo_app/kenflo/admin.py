"""Staff admin dashboard: authentication + client/request CRUD."""
from flask import (
    Blueprint, abort, flash, redirect, render_template, request,
    session, url_for,
)
from sqlalchemy import or_

from . import db
from .models import (
    CLIENT_STATUSES, Client, Note, PREFERRED_CONTACT, REQUEST_CATEGORIES,
    REQUEST_PRIORITIES, REQUEST_STATUSES, ServiceRequest, StaffUser,
    new_reference_code,
)
from .security import (
    admin_required, check_csrf, clear_failed_logins,
    current_user, is_locked_out, login_required, register_failed_login,
)

bp = Blueprint("admin", __name__)

VALID_STATUSES = {k for k, _ in REQUEST_STATUSES}
VALID_PRIORITIES = {k for k, _ in REQUEST_PRIORITIES}
VALID_CATEGORIES = {k for k, _ in REQUEST_CATEGORIES}
VALID_CLIENT_STATUSES = {k for k, _ in CLIENT_STATUSES}
VALID_CONTACT = {k for k, _ in PREFERRED_CONTACT}


def _clean(value, max_len):
    return (value or "").strip()[:max_len]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user() is not None:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        check_csrf()
        email = _clean(request.form.get("email"), 255).lower()
        password = request.form.get("password", "")

        if is_locked_out(email):
            flash("Too many failed attempts. Please wait 15 minutes and try again.", "error")
            return render_template("admin/login.html"), 429

        user = db.session.query(StaffUser).filter_by(email=email).first()
        if user is None or not user.is_active or not user.check_password(password):
            register_failed_login(email)
            flash("Invalid email or password.", "error")
            return render_template("admin/login.html"), 401

        clear_failed_logins(email)
        session.clear()
        session.permanent = True
        session["staff_id"] = user.id
        session["staff_name"] = user.name
        next_url = request.args.get("next", "")
        if next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    check_csrf()
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("public.home"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@bp.route("/")
@login_required
def dashboard():
    counts = dict(
        db.session.query(ServiceRequest.status, db.func.count(ServiceRequest.id))
        .group_by(ServiceRequest.status)
        .all()
    )
    stats = {
        "new": counts.get("new", 0),
        "open": sum(
            count for status, count in counts.items() if status not in {"completed", "closed", "declined"}
        ),
        "clients": db.session.query(db.func.count(Client.id)).scalar(),
        "requests_total": sum(counts.values()),
    }
    recent = (
        db.session.query(ServiceRequest)
        .order_by(ServiceRequest.created_at.desc())
        .limit(8)
        .all()
    )
    return render_template("admin/dashboard.html", stats=stats, recent=recent)

# ---------------------------------------------------------------------------
# Service requests
# ---------------------------------------------------------------------------


def _staff_choices():
    return db.session.query(StaffUser).filter_by(is_active=True).order_by(StaffUser.name).all()


def _apply_request_form(req, form):
    """Update a ServiceRequest from a validated admin form."""
    req.category = form.get("category") if form.get("category") in VALID_CATEGORIES else req.category
    req.status = form.get("status") if form.get("status") in VALID_STATUSES else req.status
    req.priority = form.get("priority") if form.get("priority") in VALID_PRIORITIES else req.priority
    req.name = _clean(form.get("name"), 200) or req.name
    req.email = _clean(form.get("email"), 255).lower() or None
    req.phone = _clean(form.get("phone"), 40) or None
    req.preferred_contact = (
        form.get("preferred_contact") if form.get("preferred_contact") in VALID_CONTACT else req.preferred_contact
    )
    req.service_interest = _clean(form.get("service_interest"), 200) or None
    req.organization = _clean(form.get("organization"), 200) or None
    req.city = _clean(form.get("city"), 120) or None
    req.preferred_time = _clean(form.get("preferred_time"), 120) or None
    if form.get("message"):
        req.message = _clean(form.get("message"), 5000)
    req.admin_notes = _clean(form.get("admin_notes"), 5000) or None

    assignee = form.get("assigned_to_id", "")
    if assignee in ("", "none"):
        req.assigned_to_id = None
    elif assignee.isdigit():
        staff = db.session.get(StaffUser, int(assignee))
        if staff is not None and staff.is_active:
            req.assigned_to_id = staff.id


@bp.route("/requests")
@login_required
def requests_list():
    page = max(1, request.args.get("page", 1, type=int))
    q = db.session.query(ServiceRequest)
    status = request.args.get("status", "")
    category = request.args.get("category", "")
    search = _clean(request.args.get("q"), 100)
    if status in VALID_STATUSES:
        q = q.filter(ServiceRequest.status == status)
    if category in VALID_CATEGORIES:
        q = q.filter(ServiceRequest.category == category)
    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                ServiceRequest.name.ilike(like),
                ServiceRequest.email.ilike(like),
                ServiceRequest.phone.ilike(like),
                ServiceRequest.reference_code.ilike(like),
                ServiceRequest.organization.ilike(like),
            )
        )
    pagination = db.paginate(
        q.order_by(ServiceRequest.created_at.desc()), page=page, per_page=20, error_out=False
    )
    return render_template(
        "admin/requests.html",
        pagination=pagination,
        categories=REQUEST_CATEGORIES,
        statuses=REQUEST_STATUSES,
        filters=request.args,
    )


@bp.route("/requests/new", methods=["GET", "POST"])
@login_required
def request_new():
    if request.method == "POST":
        check_csrf()
        name = _clean(request.form.get("name"), 200)
        message = _clean(request.form.get("message"), 5000)
        if not name or not message:
            flash("Name and message are required.", "error")
            return render_template("admin/request-form.html", req=None, staff=_staff_choices()), 400
        req = ServiceRequest(reference_code=new_reference_code("KF-O"), name=name, message=message, status="new")
        _apply_request_form(req, request.form)
        db.session.add(req)
        db.session.commit()
        flash(f"Request {req.reference_code} created.", "success")
        return redirect(url_for("admin.request_detail", request_id=req.id))


@bp.route("/requests/<int:request_id>")
@login_required
def request_detail(request_id):
    req = db.session.get(ServiceRequest, request_id)
    if req is None:
        abort(404)
    return render_template("admin/request-detail.html", req=req, staff=_staff_choices())


@bp.route("/requests/<int:request_id>/update", methods=["POST"])
@login_required
def request_update(request_id):
    check_csrf()
    req = db.session.get(ServiceRequest, request_id)
    if req is None:
        abort(404)
    _apply_request_form(req, request.form)
    db.session.commit()
    flash(f"Request {req.reference_code} updated.", "success")
    return redirect(url_for("admin.request_detail", request_id=req.id))


@bp.route("/requests/<int:request_id>/notes", methods=["POST"])
@login_required
def request_add_note(request_id):
    check_csrf()
    req = db.session.get(ServiceRequest, request_id)
    if req is None:
        abort(404)
    body = _clean(request.form.get("body"), 2000)
    if not body:
        flash("Note cannot be empty.", "error")
        return redirect(url_for("admin.request_detail", request_id=req.id))
    db.session.add(Note(request_id=req.id, author_id=current_user().id, body=body))
    db.session.commit()
    flash("Note added.", "success")
    return redirect(url_for("admin.request_detail", request_id=req.id))


@bp.route("/requests/<int:request_id>/convert", methods=["POST"])
@login_required
def request_convert(request_id):
    """Turn an inbound request into a tracked client record."""
    check_csrf()
    req = db.session.get(ServiceRequest, request_id)
    if req is None:
        abort(404)
    if req.client_id is not None:
        flash("This request is already linked to a client.", "warning")
        return redirect(url_for("admin.request_detail", request_id=req.id))

    parts = (req.name or "").strip().split(maxsplit=1)
    first = parts[0] or "Unknown"
    last = parts[1] if len(parts) > 1 else "(name pending)"
    client = Client(
        first_name=first,
        last_name=last,
        email=req.email,
        phone=req.phone,
        preferred_contact=req.preferred_contact,
        city=req.city,
        status="active",
        notes=f"Converted from request {req.reference_code} ({req.category}).",
    )
    db.session.add(client)
    db.session.flush()
    req.client_id = client.id
    if req.status in {"new", "in_review"}:
        req.status = "contacted"
    db.session.commit()
    flash(f"Client created and linked to this request.", "success")
    return redirect(url_for("admin.client_detail", client_id=client.id))


@bp.route("/requests/<int:request_id>/delete", methods=["POST"])
@login_required
def request_delete(request_id):
    check_csrf()
    req = db.session.get(ServiceRequest, request_id)
    if req is None:
        abort(404)
    db.session.delete(req)
    db.session.commit()
    flash("Request deleted.", "success")
    return redirect(url_for("admin.requests_list"))


@bp.route("/requests/<int:request_id>/edit", methods=["GET"])
@login_required
def request_edit(request_id):
    req = db.session.get(ServiceRequest, request_id)
    if req is None:
        abort(404)
    return render_template("admin/request-form.html", req=req, staff=_staff_choices())


# ---------------------------------------------------------------------------
# Clients CRUD
# ---------------------------------------------------------------------------


def _apply_client_form(client, form):
    client.first_name = _clean(form.get("first_name"), 100)
    client.last_name = _clean(form.get("last_name"), 100)
    client.email = _clean(form.get("email"), 255).lower() or None
    client.phone = _clean(form.get("phone"), 40) or None
    pc = form.get("preferred_contact")
    client.preferred_contact = pc if pc in VALID_CONTACT else client.preferred_contact
    client.city = _clean(form.get("city"), 120) or None
    client.language = _clean(form.get("language"), 80) or None
    client.age_group = _clean(form.get("age_group"), 40) or None
    client.referred_by = _clean(form.get("referred_by"), 200) or None
    st = form.get("status")
    client.status = st if st in VALID_CLIENT_STATUSES else client.status
    client.notes = _clean(form.get("notes"), 5000) or None


@bp.route("/clients")
@login_required
def clients_list():
    page = max(1, request.args.get("page", 1, type=int))
    q = db.session.query(Client)
    search = _clean(request.args.get("q"), 100)
    status = request.args.get("status", "")
    if status in VALID_CLIENT_STATUSES:
        q = q.filter(Client.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(
                Client.first_name.ilike(like),
                Client.last_name.ilike(like),
                Client.email.ilike(like),
                Client.phone.ilike(like),
                Client.city.ilike(like),
            )
        )
    pagination = db.paginate(q.order_by(Client.created_at.desc()), page=page, per_page=20, error_out=False)
    return render_template("admin/clients.html", pagination=pagination, filters=request.args,
                           client_statuses=CLIENT_STATUSES)


@bp.route("/clients/new", methods=["GET", "POST"])
@login_required
def client_new():
    if request.method == "POST":
        check_csrf()
        if not _clean(request.form.get("first_name"), 100) or not _clean(request.form.get("last_name"), 100):
            flash("First and last name are required.", "error")
            return render_template("admin/client-form.html", client=None), 400
        client = Client(first_name="", last_name="", preferred_contact="email")
        _apply_client_form(client, request.form)
        db.session.add(client)
        db.session.commit()
        flash(f"Client “{client.full_name}” created.", "success")
        return redirect(url_for("admin.client_detail", client_id=client.id))
    return render_template("admin/client-form.html", client=None)


@bp.route("/clients/<int:client_id>")
@login_required
def client_detail(client_id):
    client = db.session.get(Client, client_id)
    if client is None:
        abort(404)
    reqs = (
        db.session.query(ServiceRequest)
        .filter_by(client_id=client.id)
        .order_by(ServiceRequest.created_at.desc())
        .all()
    )
    return render_template("admin/client-detail.html", client=client, reqs=reqs)


@bp.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
@login_required
def client_edit(client_id):
    client = db.session.get(Client, client_id)
    if client is None:
        abort(404)
    if request.method == "POST":
        check_csrf()
        _apply_client_form(client, request.form)
        if not client.first_name or not client.last_name:
            flash("First and last name are required.", "error")
            return render_template("admin/client-form.html", client=client), 400
        db.session.commit()
        flash("Client updated.", "success")
        return redirect(url_for("admin.client_detail", client_id=client.id))
    return render_template("admin/client-form.html", client=client)


@bp.route("/clients/<int:client_id>/delete", methods=["POST"])
@login_required
def client_delete(client_id):
    check_csrf()
    client = db.session.get(Client, client_id)
    if client is None:
        abort(404)
    # Detach (do not cascade-delete) linked service requests — keep the audit trail.
    db.session.query(ServiceRequest).filter_by(client_id=client.id).update({"client_id": None})
    db.session.delete(client)
    db.session.commit()
    flash("Client deleted. Linked requests were kept in the archive.", "success")
    return redirect(url_for("admin.clients_list"))


# ---------------------------------------------------------------------------
# Staff user management (admins only) + own account
# ---------------------------------------------------------------------------


@bp.route("/users")
@admin_required
def users_list():
    users = db.session.query(StaffUser).order_by(StaffUser.name).all()
    return render_template("admin/users.html", users=users)


@bp.route("/users/new", methods=["GET", "POST"])
@admin_required
def user_new():
    if request.method == "POST":
        check_csrf()
        import re

        name = _clean(request.form.get("name"), 120)
        email = _clean(request.form.get("email"), 255).lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "staff")
        errors = []
        if not name:
            errors.append("Name is required.")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""):
            errors.append("A valid email is required.")
        if len(password) < 10:
            errors.append("Password must be at least 10 characters.")
        if role not in {"admin", "staff"}:
            role = "staff"
        if db.session.query(StaffUser).filter_by(email=email).first() is not None:
            errors.append("A user with that email already exists.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/user-form.html", user=None), 400

        user = StaffUser(name=name, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"Staff user {name} created.", "success")
        return redirect(url_for("admin.users_list"))
    return render_template("admin/user-form.html", user=None)


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def user_edit(user_id):
    user = db.session.get(StaffUser, user_id)
    if user is None:
        abort(404)
    if request.method == "POST":
        check_csrf()
        user.name = _clean(request.form.get("name"), 120) or user.name
        role = request.form.get("role", user.role)
        if role in {"admin", "staff"}:
            user.role = role
        # Guard: never demote/deactivate the last active admin.
        if user.role != "admin" or not user.is_active:
            last_admin = (
                db.session.query(StaffUser)
                .filter(StaffUser.role == "admin", StaffUser.is_active.is_(True), StaffUser.id != user.id)
                .count()
                == 0
            )
            if last_admin:
                flash("Cannot demote or deactivate the last active administrator.", "error")
                return redirect(url_for("admin.user_edit", user_id=user.id))
        user.role = role if role in {"admin", "staff"} else user.role
        user.is_active = bool(request.form.get("is_active"))
        new_password = request.form.get("password", "")
        if new_password:
            if len(new_password) < 10:
                flash("Password must be at least 10 characters.", "error")
                return render_template("admin/user-form.html", user=user), 400
            user.set_password(new_password)
        db.session.commit()
        flash("User updated.", "success")
        return redirect(url_for("admin.users_list"))
    return render_template("admin/user-form.html", user=user)


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def user_delete(user_id):
    check_csrf()
    user = db.session.get(StaffUser, user_id)
    if user is None:
        abort(404)
    if user.id == current_user().id:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("admin.users_list"))
    last_admin = (
        db.session.query(StaffUser)
        .filter(StaffUser.role == "admin", StaffUser.is_active.is_(True), StaffUser.id != user.id)
        .count()
        == 0
    )
    if last_admin:
        flash("Cannot delete the last active administrator.", "error")
        return redirect(url_for("admin.users_list"))
    db.session.delete(user)
    db.session.commit()
    flash("User deleted.", "success")
    return redirect(url_for("admin.users_list"))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    user = current_user()
    if request.method == "POST":
        check_csrf()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        if not user.check_password(current_password):
            flash("Current password is incorrect.", "error")
        elif len(new_password) < 10:
            flash("New password must be at least 10 characters.", "error")
        else:
            user.set_password(new_password)
            db.session.commit()
            flash("Password changed.", "success")
        return redirect(url_for("admin.account"))
    return render_template("admin/account.html", user=user)

