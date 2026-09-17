"""Public marketing site + client intake form."""
import os
import re

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from . import db
from .models import PREFERRED_CONTACT, REQUEST_CATEGORIES, ServiceRequest, new_reference_code
from .security import check_csrf

bp = Blueprint("public", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

VALID_CATEGORIES = {k for k, _ in REQUEST_CATEGORIES}
VALID_CONTACT = {k for k, _ in PREFERRED_CONTACT}

# ---------------------------------------------------------------------------
# Public team directory — single source of truth for the "Meet the Team" page.
#
# To publish a portrait, drop the file named in "photo" into kenflo/static/images/.
# The page checks for it at render time and swaps the monogram for the photo, so
# no template change is needed. Only publish business contact details here: this
# list is rendered on a public page. Personal/mobile numbers must stay out — see
# the notes in the team template.
# ---------------------------------------------------------------------------
STAFF = [
    {
        # "Dr (Pr.)" is an academic/doctorate title, not a clinical licence, and the
        # licence status is being verified separately with the MN Board of Psychology.
        # An optional "credential" (e.g. "PhD in Public Health") can be filled in
        # below and is rendered after the name; while it is blank, only the name
        # shown here is displayed.
        "name": "Dr (Pr.) Kennedy M. Nyachiro",
        "credential": "",
        "role": "Executive Officer — Programs",
        "email": "dken@kenfloehs.com",
        "phone": "+1 763 762 0658",
        "phone_href": "+17637620658",
        "phone_label": "Office",
        "photo": "staff1.png",
        "initials": "KN",
        "focus": "Program design and delivery, facilitation, partnership development, and community education.",
    },
    {
        "name": "Florence M. Bosire",
        "credential": "",
        "role": "Executive Officer — Administration",
        "email": "info@kenfloehs.com",
        "phone": "+1 763 762 0658",
        "phone_href": "+17637620658",
        "phone_label": "Office",
        "photo": "staff2.png",
        "initials": "FB",
        "focus": "Client intake and scheduling, records, communications, and day-to-day operations.",
    },
]


@bp.app_template_filter("dt")
def format_dt(value, fmt="%b %d, %Y"):
    if value is None:
        return ""
    return value.strftime(fmt)


def _clean(value: str, max_len: int) -> str:
    return (value or "").strip()[:max_len]


def _validate_contact_payload(form, require_message=True):
    """Shared validation for the public intake form. Returns (data, errors)."""
    errors = []
    data = {
        "name": _clean(form.get("name"), 200),
        "email": _clean(form.get("email"), 255).lower(),
        "phone": _clean(form.get("phone"), 40),
        "preferred_contact": _clean(form.get("preferred_contact"), 20) or "email",
        "category": _clean(form.get("category"), 30) or "support",
        "service_interest": _clean(form.get("service_interest"), 200),
        "organization": _clean(form.get("organization"), 200),
        "city": _clean(form.get("city"), 120),
        "message": _clean(form.get("message"), 5000),
        "preferred_time": _clean(form.get("preferred_time"), 120),
    }

    if not data["name"]:
        errors.append("Please tell us your name.")
    if not data["email"] and not data["phone"]:
        errors.append("Please provide either an email address or a phone number.")
    if data["email"] and not EMAIL_RE.match(data["email"]):
        errors.append("That email address does not look valid.")
    if data["preferred_contact"] not in VALID_CONTACT:
        data["preferred_contact"] = "email"
    if data["category"] not in VALID_CATEGORIES:
        data["category"] = "general"
    if require_message and not data["message"]:
        errors.append("Please include a short message describing the support you are looking for.")
    if data["message"] and len(data["message"]) < 5:
        errors.append("Your message is too short — please add a little more detail.")
    return data, errors


@bp.route("/")
def home():
    return render_template("public/home.html", seo_title=current_app.config["SEO_TITLE"],
                           seo_description=current_app.config["SEO_DESCRIPTION"])


@bp.route("/about")
def about():
    return render_template("public/about.html")


@bp.route("/services")
def services():
    return render_template("public/services.html")


@bp.route("/groups-workshops")
def groups_workshops():
    return render_template("public/groups-workshops.html")


@bp.route("/youth-schools")
def youth_schools():
    return render_template("public/youth-schools.html")


@bp.route("/organizations")
def organizations():
    return render_template("public/organizations.html")


@bp.route("/team")
def team():
    """Public staff directory. Portraits are optional — see STAFF above."""
    images_dir = os.path.join(current_app.static_folder, "images")
    members = []
    for person in STAFF:
        member = dict(person)
        member["has_photo"] = os.path.isfile(os.path.join(images_dir, person["photo"]))
        members.append(member)
    return render_template("public/team.html", team=members)


@bp.route("/cultural-support")
def cultural_support():
    return render_template("public/cultural-support.html")


@bp.route("/resources")
def resources():
    return render_template("public/resources.html")


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        return render_template("public/contact.html", form={})

    check_csrf()
    data, errors = _validate_contact_payload(request.form)
    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("public/contact.html", form=data), 400

    req = ServiceRequest(
        reference_code=new_reference_code("KF-W"),
        category=data["category"],
        service_interest=data["service_interest"] or None,
        name=data["name"],
        email=data["email"] or None,
        phone=data["phone"] or None,
        preferred_contact=data["preferred_contact"],
        organization=data["organization"] or None,
        city=data["city"] or None,
        message=data["message"],
        preferred_time=data["preferred_time"] or None,
        status="new",
        priority="normal",
    )
    db.session.add(req)
    db.session.commit()
    current_app.logger.info("New website request %s from %s", req.reference_code, data["name"])

    # Post/Redirect/Get so a refresh cannot duplicate the submission.
    return redirect(url_for("public.contact_success", ref=req.reference_code))


@bp.route("/contact/success")
def contact_success():
    ref = _clean(request.args.get("ref"), 16)
    if not ref or not re.fullmatch(r"KF-W-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}", ref):
        abort(404)
    req = db.session.query(ServiceRequest).filter_by(reference_code=ref).first()
    if req is None:
        abort(404)
    return render_template("public/contact-success.html", ref=ref, req=req)
