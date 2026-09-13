#!/usr/bin/env bash
# =============================================================================
# KENFLO — DigitalOcean deployment script (Ubuntu 24.04 droplet)
#
# Runs from your local machine, pushes the app code over SSH with rsync and
# provisions the server (nginx + systemd + gunicorn + optional Let's Encrypt).
#
# Requirements (local machine):
#   - rsync, bash 4+
#   - SSH access to the droplet (key: kenflo_app/kenflo_app)
#
# Usage:
#   DOMAIN=kenflo.example.com                \
#   ADMIN_EMAIL=admin@kenflo.org             \
#   ADMIN_PASSWORD='<long-random-password>'  \
#   ./deploy/deploy.sh root@<droplet-ip>
#
#   If DOMAIN is set, certbot issues HTTPS certs for it (DNS must point at the
#   droplet first). If DOMAIN is empty, the site is served over HTTP on the
#   droplet IP (good for a first smoke test).
#
# Idempotent: safe to re-run for app updates (restarts the service).
# =============================================================================
set -euo pipefail

SSH_TARGET="${1:?Usage: $0 root@<droplet-ip> [domain]}"
DOMAIN="${DOMAIN:-${2:-}}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@kenflo.org}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSH_KEY="${SSH_PRIVATE_KEY:-$APP_DIR/kenflo_app}"
REMOTE_APP="/opt/kenflo/kenflo_app"
SSH_OPTS=(-i "$SSH_KEY" -o ConnectTimeout=15 -o BatchMode=yes)

command -v rsync >/dev/null || { echo "ERROR: rsync is required locally" >&2; exit 1; }
[[ -f "$SSH_KEY" ]] || { echo "ERROR: SSH key not found: $SSH_KEY" >&2; exit 1; }

if [[ -z "$ADMIN_PASSWORD" ]]; then
  echo "ERROR: export ADMIN_PASSWORD='<long-random-password>' (>=10 chars)" >&2
  exit 1
fi
if [[ "${#ADMIN_PASSWORD}" -lt 10 ]]; then
  echo "ERROR: ADMIN_PASSWORD must be at least 10 characters" >&2
  exit 1
fi

echo "==> [1/7] Checking SSH connectivity to $SSH_TARGET"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'echo "  OK: connected to $(hostname) as $(whoami)"'

echo "==> [2/7] Pushing app code to $REMOTE_APP (rsync)"
rsync -az --delete \
  -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new" \
  --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='instance/' --exclude='*.db' --exclude='.env' \
  --exclude='kenflo_app' --exclude='kenflo_app.pub' \
  "$APP_DIR/" "$SSH_TARGET:$REMOTE_APP"

echo "==> [3/7] Provisioning server (packages, user, venv, dependencies)"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'bash -s' <<'REMOTE_PROVISION'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
echo "  -- installing system packages"
apt-get update -y
apt-get install -y python3-venv python3-pip nginx certbot ufw

echo "  -- creating kenflo service user + directories"
id kenflo >/dev/null 2>&1 || \
  useradd --system --create-home --home-dir /opt/kenflo --shell /usr/sbin/nologin kenflo
usermod -aG www-data kenflo
mkdir -p /opt/kenflo /etc/kenflo
chown -R kenflo:www-data /opt/kenflo
chmod g+w /opt/kenflo

echo "  -- creating Python venv + installing requirements"
if [[ ! -x "$REMOTE_APP/.venv/bin/python" ]]; then
  sudo -u kenflo python3 -m venv "$REMOTE_APP/.venv"
  sudo -u kenflo "$REMOTE_APP/.venv/bin/pip" install --upgrade pip
fi
sudo -u kenflo "$REMOTE_APP/.venv/bin/pip" install -r "$REMOTE_APP/requirements.txt"

echo "  -- writing /etc/kenflo/kenflo.env (secret key)"
if [[ ! -f /etc/kenflo/kenflo.env ]] || ! grep -q '^KENFLO_SECRET_KEY=' /etc/kenflo/kenflo.env; then
  umask 077
  printf 'KENFLO_SECRET_KEY=%s\n' "$(openssl rand -hex 32)" > /etc/kenflo/kenflo.env
  chown root:root /etc/kenflo/kenflo.env
  chmod 600 /etc/kenflo/kenflo.env
fi
grep -q '^KENFLO_COOKIE_SECURE=' /etc/kenflo/kenflo.env || echo 'KENFLO_COOKIE_SECURE=1' >> /etc/kenflo/kenflo.env
REMOTE_PROVISION

echo "==> [4/7] Installing systemd unit + starting kenflo.service"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'bash -s' <<'REMOTE_SYSTEMD'
set -euo pipefail
REMOTE_APP="/opt/kenflo/kenflo_app"
cp -f "$REMOTE_APP/deploy/kenflo.service" /etc/systemd/system/kenflo.service
systemctl daemon-reload
systemctl enable kenflo >/dev/null 2>&1 || true
systemctl restart kenflo
# wait for Type=notify READY
for i in $(seq 1 30); do
  systemctl is-active --quiet kenflo && break
  sleep 1
done
systemctl --no-pager status kenflo --full || true
systemctl is-active kenflo >/dev/null \
  || { echo "ERROR: kenflo.service failed to start"; journalctl -u kenflo -n 40 --no-pager; exit 1; }
REMOTE_SYSTEMD

echo "==> [5/7] Configuring nginx reverse proxy"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "DOMAIN='${DOMAIN}'" 'bash -s' <<'REMOTE_NGINX'
set -euo pipefail
DOMAIN="${DOMAIN:-_}"
cat > /etc/nginx/sites-available/kenflo.conf <<EOF
# KENFLO nginx site — rendered by deploy.sh
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    # --- Security headers ---
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;

    # --- Basic hardening ---
    client_max_body_size 1m;
    server_tokens off;

    # Block common probe paths
    location ~ /(\.git|\.env|\.ht) { deny all; return 404; }

    # --- Static assets directly by nginx ---
    location /static/ {
        alias /opt/kenflo/kenflo_app/kenflo/static/;
        expires 7d;
        access_log off;
        add_header Cache-Control "public, max-age=604800";
    }

    # --- Gunicorn over Unix socket ---
    location / {
        include proxy_params;
        proxy_pass http://unix:/run/kenflo/kenflo.sock;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
    }

    # --- Gzip ---
    gzip on;
    gzip_types text/plain text/css application/json application/javascript image/svg+xml;
    gzip_min_length 1024;
}
EOF
ln -sf /etc/nginx/sites-available/kenflo.conf /etc/nginx/sites-enabled/kenflo.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
REMOTE_NGINX
echo "==> [6/7] Seeding the admin account"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
  "ADMIN_EMAIL='${ADMIN_EMAIL}' ADMIN_PASSWORD='${ADMIN_PASSWORD}'" 'bash -s' <<'REMOTE_SEED'
set -euo pipefail
REMOTE_APP="/opt/kenflo/kenflo_app"
# load KENFLO_SECRET_KEY so create_app() can build (idempotent) session cookies
set -a; . /etc/kenflo/kenflo.env; set +a
export KENFLO_ADMIN_EMAIL="$ADMIN_EMAIL" KENFLO_ADMIN_PASSWORD="$ADMIN_PASSWORD"
cd "$REMOTE_APP"
sudo -u kenflo ./.venv/bin/flask --app run.py seed-admin
REMOTE_SEED

echo "==> [7/7] HTTPS via Let's Encrypt (if DOMAIN provided)"
if [[ -n "$DOMAIN" ]]; then
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" \
    "DOMAIN='${DOMAIN}' ADMIN_EMAIL='${ADMIN_EMAIL}'" 'bash -s' <<'REMOTE_CERTBOT'
set -euo pipefail
if ! command -v certbot >/dev/null 2>&1; then
  apt-get install -y certbot >/dev/null 2>&1 || true
fi
certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m "${ADMIN_EMAIL}" --redirect || \
  echo "WARNING: certbot failed — check that DNS for ${DOMAIN} points to this droplet."
REMOTE_CERTBOT
else
  echo "  (no DOMAIN set — skipping TLS; serving over HTTP)"
fi

echo
echo "==> Final health checks"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'bash -s' <<'REMOTE_HEALTH'
set -euo pipefail
echo "-- systemd"
systemctl is-active kenflo && echo "kenflo.service: ACTIVE"
echo "-- local HTTP status (through nginx)"
curl -s -o /dev/null -w '  HTTP %{http_code} (%{time_total}s)\n' http://127.0.0.1/ || echo "  FAILED"
echo "-- listening sockets"
ss -tlnp | grep -E ':80|:443' || true
echo "-- recent kenflo logs"
journalctl -u kenflo -n 6 --no-pager || true
REMOTE_HEALTH

PUBLIC_IP="${SSH_TARGET#*@}"
echo
echo "=========================================================="
echo " DEPLOYMENT COMPLETE"
[[ -n "$DOMAIN" ]] && echo " Public URL : https://${DOMAIN}" || echo " Public URL : http://${PUBLIC_IP}"
echo " Staff login: /admin/login"
echo " DB backup  : sqlite3 /opt/kenflo/kenflo_app/instance/kenflo.db '.backup ...'"
echo " Logs       : journalctl -u kenflo -f"
echo "=========================================================="