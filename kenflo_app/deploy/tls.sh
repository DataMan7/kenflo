#!/usr/bin/env bash
# =============================================================================
# KENFLO — TLS finish step (run AFTER pointing your domain at the droplet).
#
#   1. Preflight: verifies ${DOMAIN} resolves to the droplet IP.
#   2. Issues Let's Encrypt certs for ${DOMAIN} + www.${DOMAIN} via certbot/nginx.
#   3. Sets KENFLO_COOKIE_SECURE=1 and restarts the app (secure session cookies).
#   4. Verifies HTTPS on the origin.
#
# Usage:
#   ./deploy/tls.sh root@<droplet-ip>
#
# Domain defaults to kenfloehs.com (override with DOMAIN=... ADMIN_EMAIL=...).
# Requires the domain A record (DNS-only is fine; proxied works too once the
# origin behind Cloudflare is this droplet) to reach this droplet.
# =============================================================================
set -euo pipefail

SSH_TARGET="${1:?Usage: $0 root@<droplet-ip>}"
DOMAIN="${DOMAIN:-kenfloehs.com}"
ADMIN_EMAIL="${ADMIN_EMAIL:-m.oomboga@gmail.com}"
DROPLET_IP="${SSH_TARGET#*@}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- SSH key selection (mirrors deploy.sh) ----------------------------------
if [[ -n "${SSH_PRIVATE_KEY:-}" ]]; then
  SSH_KEY="$SSH_PRIVATE_KEY"
  [[ -f "$SSH_KEY" ]] || { echo "ERROR: SSH_PRIVATE_KEY not found: $SSH_KEY" >&2; exit 1; }
  SSH_OPTS=(-i "$SSH_KEY" -o ConnectTimeout=15 -o BatchMode=yes)
else
  SSH_OPTS=(-o ConnectTimeout=15 -o BatchMode=yes)
fi

command -v dig >/dev/null || { echo "ERROR: dig (dnsutils) required locally" >&2; exit 1; }

echo "==> [1/5] SSH connectivity"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'echo "  OK: connected to $(hostname) as $(whoami)"'

echo "==> [2/5] DNS preflight: ${DOMAIN} -> $DROPLET_IP"
RESOLVED="$(dig +short "$DOMAIN" A | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | head -5)"
echo "  ${DOMAIN} A = ${RESOLVED//$'\n'/ }"
if ! grep -qF "$DROPLET_IP" <<<"$RESOLVED"; then
  echo "ERROR: ${DOMAIN} does not resolve to $DROPLET_IP yet." >&2
  echo "  In Cloudflare DNS, point the @ A record at $DROPLET_IP and wait" >&2
  echo "  for propagation, then re-run this script. (www follows the CNAME.)" >&2
  exit 1
fi
echo "  OK: DNS targets the droplet."

echo "==> [3/5] Issuing Let's Encrypt certificates ($DOMAIN, www.$DOMAIN)"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "DOMAIN='$DOMAIN' ADMIN_EMAIL='$ADMIN_EMAIL'" 'bash -s' <<'REMOTE_CERTBOT'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
command -v certbot >/dev/null 2>&1 || apt-get install -y certbot >/dev/null 2>&1 || true
# certbot --nginx requires the nginx plugin; install it if missing.
python3 - <<'PY' >/dev/null 2>&1 || apt-get install -y python3-certbot-nginx >/dev/null 2>&1 || true
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec("certbot_nginx") else 1)
PY
# --nginx inserts the challenges into the kenflo site and reloads nginx.
certbot --nginx -d "${DOMAIN}" -d "www.${DOMAIN}" \
        --non-interactive --agree-tos -m "${ADMIN_EMAIL}" --redirect
REMOTE_CERTBOT

echo "==> [4/5] Enabling secure session cookies (KENFLO_COOKIE_SECURE=1)"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'bash -s' <<'REMOTE_SECURE'
set -euo pipefail
sed -i 's/^KENFLO_COOKIE_SECURE=0$/KENFLO_COOKIE_SECURE=1/' /etc/kenflo/kenflo.env
grep '^KENFLO_COOKIE_SECURE=' /etc/kenflo/kenflo.env
systemctl restart kenflo
sleep 3
systemctl is-active kenflo
REMOTE_SECURE

echo "==> [5/5] HTTPS verification (origin side)"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" 'bash -s' <<'REMOTE_VERIFY'
set -euo pipefail
echo "-- nginx HTTPS listener"
ss -tlnp | grep ':443' || true
for d in /etc/letsencrypt/live/*/; do
  echo "-- cert: $d"; ls "$d"; done
echo "-- origin HTTPS status"
curl -sk -o /dev/null -w "  https://127.0.0.1/ -> HTTP %{http_code}\n" -H "Host: kenfloehs.com" https://127.0.0.1/ || true
REMOTE_VERIFY

echo
echo "================ DONE ================"
echo " Certs issued for: ${DOMAIN} + www.${DOMAIN}"
echo " Secure cookies:   ON"
echo " NEXT (Cloudflare): set @ and www back to Proxied (orange cloud)"
echo "                    and SSL/TLS mode to 'Full (strict)'."
echo " Then verify:  https://${DOMAIN}  and  https://www.${DOMAIN}"
echo "======================================"