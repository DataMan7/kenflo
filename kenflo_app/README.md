# KENFLO Emotional Health Services LLC — Website + Client-Handling App

A production-ready **Flask** web application for KENFLO Emotional Health Services LLC:

- **Public website** — Home, About, Individual & Family Services, Groups & Workshops,
  Youth & Schools, Organizations & Communities, Cultural & Immigration Support,
  Resources (with 911/988 crisis notice), and a Contact / Get Support intake form.
- **Staff portal (CRUD)** — securely handle clients from the website:
  - Dashboard with request statistics
  - **Service Requests** — every website submission arrives here with a reference
    number (e.g. `KF-W-7Q2M4D`); staff can create, read, update, delete, filter,
    search, assign, prioritize, add activity notes, and convert a request into a client.
  - **Clients** — full CRUD with search/filter/status.
  - **Staff users** — admin-only management (create, edit, deactivate, delete,
    password resets) with last-admin protection.
- **Security** — password hashing (Werkzeug/scrypt), per-session CSRF tokens,
  HttpOnly/SameSite cookies, login lockout (5 attempts / 15 min), server-side
  validation, parameterized queries, hardened nginx config.
- **Deployment** — Gunicorn + Nginx (Unix socket) + systemd, SQLite by default,
  PostgreSQL-ready via `DATABASE_URL`.

## Project layout

```
kenflo_app/
├── run.py                  # dev server entry point
├── config.py               # env-driven configuration
├── gunicorn.conf.py        # production WSGI config (unix socket)
├── requirements.txt
├── deploy/
│   ├── nginx-kenflo.conf   # nginx site config
│   └── kenflo.service      # systemd unit
└── kenflo/
    ├── __init__.py         # app factory + CLI (flask seed-admin)
    ├── models.py           # StaffUser, Client, ServiceRequest, Note
    ├── security.py         # auth, CSRF, lockout helpers
    ├── public.py           # marketing pages + intake form
    ├── admin.py            # staff portal CRUD
    ├── templates/          # Jinja2 templates
    └── static/             # CSS + JS (no build step)
```

## Run locally

```bash
cd kenflo_app
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# create the first admin account
KENFLO_ADMIN_EMAIL=admin@kenflo.org KENFLO_ADMIN_PASSWORD='change-me-please' flask --app run.py seed-admin
# (or with the app package: FLASK_APP=run.py flask seed-admin)

python run.py            # http://127.0.0.1:5000
# staff portal: http://127.0.0.1:5000/admin/login
```

The SQLite database is created automatically at `instance/kenflo.db`.

## Deploy with nginx (Ubuntu)

```bash
# 1. Copy the code to the server
sudo mkdir -p /opt/kenflo && sudo cp -r kenflo_app /opt/kenflo/
cd /opt/kenflo/kenflo_app
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt

# 2. Create admin user
KENFLO_ADMIN_EMAIL=admin@kenflo.org \
KENFLO_ADMIN_PASSWORD='<long-random-password>' \
./.venv/bin/flask --app run.py seed-admin

# 3. Permissions
sudo chown -R kenflo:www-data /opt/kenflo

# 4. Systemd
sudo cp deploy/kenflo.service /etc/systemd/system/
#    edit KENFLO_SECRET_KEY + User inside the unit first!
sudo systemctl daemon-reload && sudo systemctl enable --now kenflo

# 5. Nginx
sudo cp deploy/nginx-kenflo.conf /etc/nginx/sites-available/kenflo.conf
sudo ln -s /etc/nginx/sites-available/kenflo.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 6. HTTPS
sudo certbot --nginx -d kenflo.example.com
```

### PostgreSQL (recommended in production)

```bash
sudo -u postgres psql -c "CREATE USER kenflo WITH PASSWORD '...';"
sudo -u postgres psql -c "CREATE DATABASE kenflo OWNER kenflo;"
# in the systemd unit:
DATABASE_URL=postgresql+psycopg://kenflo:...@localhost/kenflo
# and: ./.venv/bin/pip install psycopg[binary]
```

## Operations

| Task | Command |
|------|---------|
| View logs | `journalctl -u kenflo -f` |
| Restart app | `sudo systemctl restart kenflo` |
| Backup DB | `sqlite3 instance/kenflo.db ".backup backup-$(date +%F).db"` |
| Reset admin password | `KENFLO_ADMIN_EMAIL=... KENFLO_ADMIN_PASSWORD=... flask --app run.py seed-admin` |

## Compliance notes

The site intentionally carries the non-clinical scope statement and the 911/988
crisis notice in the footer of every page, plus contextual disclaimers on the
contact form — per KENFLO's service-scope requirements.
