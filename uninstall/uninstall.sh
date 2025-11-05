#!/usr/bin/env bash
# SentinelServer_AI Uninstaller (root-friendly)
# - Stops & disables systemd service (sentinel)
# - Removes unit file
# - Removes repo/venv (auto-detect from .env or common paths)
# - Optionally removes DB & TLS certs (self-signed + Let's Encrypt)
# - Optionally removes NGINX reverse-proxy blocks
#
# Usage:
#   sudo bash uninstall.sh
#   sudo bash uninstall.sh --force
#   sudo bash uninstall.sh --keep-db
#   sudo bash uninstall.sh --keep-certs
#   sudo bash uninstall.sh --only-service

set -euo pipefail

APP_NAME="sentinel"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

# ---- Defaults (will be extended by .env if present)
REPO_DIRS=(
  "/root/SentinelServer_AI"
  "/home/ubuntu/SentinelServer_AI"
  "/home/ubuntu/sentinel_server"
)
VENV_DIRS=(
  "/root/SentinelServer_AI/.venv"
  "/home/ubuntu/SentinelServer_AI/.venv"
  "/home/ubuntu/sentinel/.venv"
)
DB_FILES=(
  "/root/SentinelServer_AI/db/sentinel.db"
  "/home/ubuntu/SentinelServer_AI/sentinel_server/db/sentinel.db"
  "/home/ubuntu/sentinel_server/db/sentinel.db"
  "/home/ubuntu/sentinel/db/sentinel.db"
)
# Self-signed
SELF_SIGNED_DIR="/etc/ssl/sentinel"
# Let's Encrypt (base; domain-specific path resolved later)
LE_LIVE_BASE="/etc/letsencrypt/live"
LE_ARCHIVE_BASE="/etc/letsencrypt/archive"
LE_RENEWAL_BASE="/etc/letsencrypt/renewal"
LE_RENEW_HOOK="/etc/letsencrypt/renewal-hooks/deploy/00-restart-sentinel.sh"

# NGINX (if ever used)
NGINX_AVAILABLE="/etc/nginx/sites-available/sentinel"
NGINX_ENABLED="/etc/nginx/sites-enabled/sentinel"

KEEP_DB=false
KEEP_CERTS=false
ONLY_SERVICE=false
FORCE=false

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=true ;;
    --keep-db) KEEP_DB=true ;;
    --keep-certs) KEEP_CERTS=true ;;
    --only-service) ONLY_SERVICE=true ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo $0 $*" >&2
  exit 1
fi

# ---- Try to read .env to refine paths
ENV_FILE="/root/SentinelServer_AI/setup/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -o allexport; source "$ENV_FILE"; set +o allexport
  # APP_DST/RUN_USER/DOMAIN may be defined
  if [[ -n "${APP_DST:-}" ]]; then
    # Prepend detected repo/venv/db
    REPO_DIRS=("$APP_DST" "${REPO_DIRS[@]}")
    VENV_DIRS=("$APP_DST/.venv" "${VENV_DIRS[@]}")
    DB_FILES=("$APP_DST/db/sentinel.db" "${DB_FILES[@]}")
  fi
fi

DOMAIN="${DOMAIN:-bobsentinel.com}"
LE_LIVE_DIR="${LE_LIVE_BASE}/${DOMAIN}"
LE_ARCHIVE_DIR="${LE_ARCHIVE_BASE}/${DOMAIN}"
LE_RENEW_FILE="${LE_RENEWAL_BASE}/${DOMAIN}.conf"

confirm() {
  $FORCE && return 0
  echo "=== SentinelServer_AI Uninstall ==="
  echo "Service unit : $SERVICE_FILE"
  echo "Repo cand.   : ${REPO_DIRS[*]}"
  echo "Venv cand.   : ${VENV_DIRS[*]}"
  echo "DB cand.     : ${DB_FILES[*]}"
  echo "Self-signed  : $SELF_SIGNED_DIR"
  echo "LE live      : $LE_LIVE_DIR"
  echo "LE archive   : $LE_ARCHIVE_DIR"
  echo "LE renewal   : $LE_RENEW_FILE"
  echo "LE hook      : $LE_RENEW_HOOK"
  echo "NGINX        : $NGINX_AVAILABLE , $NGINX_ENABLED"
  echo "Flags -> force:$FORCE keep-db:$KEEP_DB keep-certs:$KEEP_CERTS only-service:$ONLY_SERVICE"
  read -r -p "Proceed to uninstall? Type YES to continue: " ans
  [[ "$ans" == "YES" ]]
}

confirm || { echo "Cancelled."; exit 0; }

echo "-> Stopping & disabling service (if present)"
if systemctl list-unit-files | grep -q "^${APP_NAME}.service"; then
  systemctl stop "${APP_NAME}" || true
  systemctl disable "${APP_NAME}" || true
  systemctl reset-failed "${APP_NAME}" || true
else
  echo "   ${APP_NAME}.service not registered (ok)."
fi

echo "-> Removing systemd unit file"
if [[ -f "$SERVICE_FILE" ]]; then
  rm -f "$SERVICE_FILE"
  systemctl daemon-reload
  echo "   Removed $SERVICE_FILE and reloaded systemd."
else
  echo "   No unit at $SERVICE_FILE (ok)."
fi

if [[ "$ONLY_SERVICE" == "true" ]]; then
  echo "Only service removed (--only-service)."
  exit 0
fi

echo "-> Removing NGINX blocks (if any)"
if [[ -L "$NGINX_ENABLED" ]]; then
  rm -f "$NGINX_ENABLED" || true
  echo "   Removed enabled symlink: $NGINX_ENABLED"
fi
if [[ -f "$NGINX_AVAILABLE" ]]; then
  rm -f "$NGINX_AVAILABLE" || true
  echo "   Removed available site: $NGINX_AVAILABLE"
fi
if command -v nginx >/dev/null 2>&1; then
  if nginx -t >/dev/null 2>&1; then
    systemctl reload nginx || true
  fi
fi

echo "-> Removing virtual environments"
for v in "${VENV_DIRS[@]}"; do
  [[ -d "$v" ]] && { rm -rf "$v"; echo "   Removed venv: $v"; }
done

echo "-> Removing cloned repositories"
for r in "${REPO_DIRS[@]}"; do
  [[ -d "$r" ]] && { rm -rf "$r"; echo "   Removed repo: $r"; }
done

echo "-> Handling database files"
if [[ "$KEEP_DB" == "true" ]]; then
  echo "   Keeping DB files (--keep-db)."
else
  for d in "${DB_FILES[@]}"; do
    [[ -f "$d" ]] && { rm -f "$d"; echo "   Removed DB: $d"; }
  done
fi

echo "-> Handling TLS certificates"
if [[ "$KEEP_CERTS" == "true" ]]; then
  echo "   Keeping certs (--keep-certs)."
else
  # Self-signed
  [[ -d "$SELF_SIGNED_DIR" ]] && { rm -rf "$SELF_SIGNED_DIR"; echo "   Removed self-signed dir: $SELF_SIGNED_DIR"; }
  # Let's Encrypt (domain-scoped)
  [[ -d "$LE_LIVE_DIR" ]]    && { rm -rf "$LE_LIVE_DIR";    echo "   Removed LE live: $LE_LIVE_DIR"; }
  [[ -d "$LE_ARCHIVE_DIR" ]] && { rm -rf "$LE_ARCHIVE_DIR"; echo "   Removed LE archive: $LE_ARCHIVE_DIR"; }
  [[ -f "$LE_RENEW_FILE" ]]  && { rm -f "$LE_RENEW_FILE";   echo "   Removed LE renewal conf: $LE_RENEW_FILE"; }
  [[ -f "$LE_RENEW_HOOK" ]]  && { rm -f "$LE_RENEW_HOOK";   echo "   Removed LE renewal hook: $LE_RENEW_HOOK"; }
fi

echo "-> (Optional) UFW rules cleanup - skipped"
echo "   If you want to close 80/443:"
echo "     sudo ufw delete allow 80"
echo "     sudo ufw delete allow 443"

echo
echo "Uninstall complete."
echo "You may vacuum logs if desired:"
echo "  sudo journalctl --unit=${APP_NAME} --since today"
echo "  sudo journalctl --vacuum-time=7d"
