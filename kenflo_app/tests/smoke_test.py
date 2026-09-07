"""End-to-end smoke test for the KENFLO app (uses the Flask test client)."""
import os
import re
import shutil
import sys

os.environ["KENFLO_SECRET_KEY"] = "test-secret-key-for-smoke-test"
os.environ["KENFLO_DB_DIR"] = "/tmp/kenflo-test-db"
shutil.rmtree("/tmp/kenflo-test-db", ignore_errors=True)

from kenflo import create_app
from kenflo.models import Client, Note, ServiceRequest, StaffUser, db

app = create_app()
BASE = "http://kenflo.test"
passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name} {extra}")


def csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="_csrf" value="([0-9a-f]+)"', r.data)
    return m.group(1).decode() if m else ""


with app.app_context():
    db.create_all()
    admin = StaffUser(name="Test Admin", email="admin@test.org", role="admin")
    admin.set_password("correct-horse-battery")
    db.session.add(admin)
    staff = StaffUser(name="Test Staff", email="staff@test.org", role="staff")
    staff.set_password("staff-password-123")
    db.session.add(staff)
    db.session.commit()

client = app.test_client()

print("== Public pages ==")
for path in ["/", "/about", "/services", "/groups-workshops", "/youth-schools",
             "/organizations", "/cultural-support", "/resources", "/contact"]:
    r = client.get(BASE + path)
    check(f"GET {path} -> 200", r.status_code == 200, str(r.status_code))

r = client.get(BASE + "/nonexistent")
check("GET /nonexistent -> 404", r.status_code == 404)

print("== Public intake form ==")
token = csrf(client, BASE + "/contact")
check("CSRF token present in contact form", bool(token))

r = client.post(BASE + "/contact", data={"name": "x", "message": "y"})  # no csrf
check("POST without CSRF -> 400", r.status_code == 400)

r = client.post(BASE + "/contact", data={
    "_csrf": token, "name": "Jane Doe", "email": "jane@example.org",
    "phone": "", "preferred_contact": "email", "category": "support",
    "service_interest": "Emotional Wellness Support", "city": "Minneapolis",
    "organization": "", "preferred_time": "Weekday mornings",
    "message": "I would like support managing everyday stress.",
})
check("Valid POST -> 302 redirect", r.status_code == 302, str(r.status_code))
ref = r.headers["Location"].split("ref=")[-1]
check("Reference code returned", ref.startswith("KF-W-"), ref)

r = client.get(BASE + f"/contact/success?ref={ref}")
check("Success page shows reference", r.status_code == 200 and ref.encode() in r.data)

r = client.post(BASE + "/contact", data={
    "_csrf": token, "name": "", "email": "not-an-email", "message": ""})
check("Invalid POST -> 400 with errors", r.status_code == 400)

print("== Admin auth ==")
r = client.get(BASE + "/admin/")
check("Dashboard requires login (302)", r.status_code == 302 and "/admin/login" in r.headers["Location"])

token = csrf(client, BASE + "/admin/login")
r = client.post(BASE + "/admin/login", data={"_csrf": token, "email": "admin@test.org", "password": "wrong"})
check("Wrong password -> 401", r.status_code == 401)

r = client.post(BASE + "/admin/login", data={"_csrf": token, "email": "admin@test.org", "password": "correct-horse-battery"})
check("Correct login -> 302 dashboard", r.status_code == 302)

r = client.get(BASE + "/admin/")
check("Dashboard renders", r.status_code == 200 and b"New requests" in r.data)

print("== Requests CRUD ==")
r = client.get(BASE + "/admin/requests")
check("Requests list renders", r.status_code == 200)

token = csrf(client, BASE + "/admin/requests/new")
r = client.post(BASE + "/admin/requests/new", data={
    "_csrf": token, "name": "Manual Person", "email": "manual@example.org",
    "category": "workshop", "status": "new", "priority": "high",
    "message": "Office-created workshop request.", "preferred_contact": "phone",
})
check("Create office request", r.status_code == 302)
req_id = int(r.headers["Location"].rstrip("/").split("/")[-1])

with app.app_context():
    req = db.session.get(ServiceRequest, req_id)
    check("Request persisted with KF-O ref", req.reference_code.startswith("KF-O"))

r = client.get(BASE + f"/admin/requests/{req_id}")
check("Request detail renders", r.status_code == 200 and b"Manual Person" in r.data)

token = csrf(client, BASE + f"/admin/requests/{req_id}")
r = client.post(BASE + f"/admin/requests/{req_id}/update", data={
    "_csrf": token, "status": "contacted", "priority": "urgent",
    "category": "workshop", "name": "Manual Person", "email": "manual@example.org",
    "preferred_contact": "phone", "message": "Office-created workshop request.",
    "admin_notes": "Called and left voicemail.", "assigned_to_id": "none",
})
check("Update status/priority -> 302", r.status_code == 302)

token = csrf(client, BASE + f"/admin/requests/{req_id}")
r = client.post(BASE + f"/admin/requests/{req_id}/notes", data={"_csrf": token, "body": "Follow-up email sent."})
check("Add note", r.status_code == 302)

r = client.post(BASE + f"/admin/requests/{req_id}/update", data={"name": "Manual Person", "message": "x"})
check("Update without CSRF -> 400", r.status_code == 400)

with app.app_context():
    check("Note persisted", db.session.query(Note).filter_by(request_id=req_id).count() == 1)

r = client.post(BASE + f"/admin/requests/{req_id}/convert", data={"_csrf": csrf(client, BASE + f"/admin/requests/{req_id}")})
check("Convert to client -> redirect to client page", r.status_code == 302 and "/clients/" in r.headers["Location"])
client_id = int(r.headers["Location"].rstrip("/").split("/")[-1])

print("== Clients CRUD ==")
r = client.get(BASE + "/admin/clients")
check("Clients list renders", r.status_code == 200 and b"Manual Person" in r.data)

token = csrf(client, BASE + "/admin/clients/new")
r = client.post(BASE + "/admin/clients/new", data={
    "_csrf": token, "first_name": "Alice", "last_name": "Smith",
    "email": "alice@example.org", "phone": "612-555-0100",
    "preferred_contact": "text", "status": "active", "city": "St. Paul",
})
check("Create client", r.status_code == 302)

token = csrf(client, BASE + f"/admin/clients/{client_id}/edit")
r = client.post(BASE + f"/admin/clients/{client_id}/edit", data={
    "_csrf": token, "first_name": "Manual", "last_name": "Person",
    "email": "manual@example.org", "preferred_contact": "email", "status": "active",
})
check("Edit client", r.status_code == 302)

r = client.post(BASE + f"/admin/clients/{client_id}/delete", data={"_csrf": token})
check("Delete client", r.status_code == 302)

with app.app_context():
    check("Client deleted but request kept", db.session.get(Client, client_id) is None
          and db.session.get(ServiceRequest, req_id) is not None)

print("== Filters & search ==")
r = client.get(BASE + "/admin/requests?q=Jane")
check("Search by name finds Jane", r.status_code == 200 and b"Jane Doe" in r.data)
r = client.get(BASE + "/admin/requests?status=contacted")
check("Filter by status", r.status_code == 200)

print("== Staff management (admin only) ==")
token = csrf(client, BASE + "/admin/users/new")
r = client.post(BASE + "/admin/users/new", data={
    "_csrf": token, "name": "Temp User", "email": "temp@test.org",
    "password": "short", "role": "staff"})
check("Short password rejected", r.status_code == 400)

r = client.post(BASE + "/admin/users/new", data={
    "_csrf": token, "name": "Temp User", "email": "temp@test.org",
    "password": "a-longer-password-99", "role": "staff"})
check("Create staff user", r.status_code == 302)

with app.app_context():
    admin_id = db.session.query(StaffUser).filter_by(email="admin@test.org").first().id

r = client.post(BASE + f"/admin/users/{admin_id}/delete", data={"_csrf": token})
with app.app_context():
    check("Last admin protected from delete", db.session.query(StaffUser).filter_by(email="admin@test.org").first() is not None)

print("== Role enforcement ==")
r = client.post(BASE + "/admin/logout", data={"_csrf": csrf(client, BASE + "/admin/")})
check("Logout", r.status_code == 302)

token = csrf(client, BASE + "/admin/login")
r = client.post(BASE + "/admin/login", data={"_csrf": token, "email": "staff@test.org", "password": "staff-password-123"})
check("Staff login", r.status_code == 302)

r = client.get(BASE + "/admin/users")
check("Staff cannot access user management (403)", r.status_code == 403)
r = client.get(BASE + "/admin/requests")
check("Staff CAN access requests", r.status_code == 200)
r = client.post(BASE + "/admin/logout", data={"_csrf": csrf(client, BASE + "/admin/")})
check("Staff logout", r.status_code == 302)

print(f"\nResults: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)

