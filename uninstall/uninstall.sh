#!/usr/bin/env bash
# SentinelServer_AI Uninstaller
# - Stops & disables systemd service
# - Removes service unit file
# - Removes cloned repo and common venv dirs
# - Optionally removes DB & TLS certs if they live in standard paths
# - Optionally removes NGINX reverse-proxy blocks (if present)
#
# Usage:
#   sudo bash uninstall.sh              # confirm before deleting
#   sudo bash uninstall.sh --force      # no prompt
#   sudo bash uninstall.sh --keep-db    # keep database file(s)
#   sudo bash uninstall.sh --keep-certs # keep TLS cert dir
#   sudo bash uninstall.sh --only-service # just remove systemd service, keep files
set -euo pipefail

APP_NAME="sentinel"                         # systemd unit name -> sentinel.service
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

# Common install locations (adjust if you customized paths)
REPO_DIRS=(
  "/home/ubuntu/SentinelServer_AI"
  "/home/ubuntu/sentinel_server"           # alt naming
)
# venv candidates
VENV_DIRS=(
  "/home/ubuntu/SentinelServer_AI/.venv"
  "/home/ubuntu/sentinel/.venv"
)
# DB candidates (sqlite)
DB_FILES=(
  "/home/ubuntu/SentinelServer_AI/sentinel_server/db/sentinel.db"
  "/home/ubuntu/sentinel_server/db/sentinel.db"
  "/home/ubuntu/sentinel/db/sentinel.db"
)
# TLS certs (self-signed) used in our guides
CERT_DIR="/etc/ssl/sentinel"
# NGINX sites (if you used reverse-proxy; safe to skip if not present)
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

confirm() {
  $FORCE && return 0
  read -r -p "Proceed to uninstall SentinelServer_AI and related services? Type YES to continue: " ans
  [[ "$ans" == "YES" ]]
}

echo "=== SentinelServer_AI Uninstall ==="
echo "Service unit: $SERVICE_FILE"
echo "Repo candidates: ${REPO_DIRS[*]}"
echo "Venv candidates: ${VENV_DIRS[*]}"
echo "DB candidates: ${DB_FILES[*]}"
echo "Cert dir: $CERT_DIR"
echo "NGINX blocks: $NGINX_AVAILABLE , $NGINX_ENABLED"
echo "Flags -> force:$FORCE keep-db:$KEEP_DB keep-certs:$KEEP_CERTS only-service:$ONLY_SERVICE"
echo

confirm || { echo "Cancelled."; exit 0; }

echo "-> Stopping service (if running)"
if systemctl list-unit-files | grep -q "^${APP_NAME}.service"; then
  systemctl stop "${APP_NAME}" || true
  systemctl disable "${APP_NAME}" || true
  systemctl reset-failed "${APP_NAME}" || true
else
  echo "   Service ${APP_NAME}.service not found (ok)."
fi

echo "-> Removing systemd unit file (if exists)"
if [[ -f "$SERVICE_FILE" ]]; then
  rm -f "$SERVICE_FILE"
  systemctl daemon-reload
  echo "   Removed $SERVICE_FILE and reloaded systemd."
else
  echo "   No service file at $SERVICE_FILE (ok)."
fi

if [[ "$ONLY_SERVICE" == "true" ]]; then
  echo "Only service removed as requested (--only-service)."
  exit 0
fi

echo "-> Removing NGINX reverse-proxy blocks (if exist)"
if [[ -L "$NGINX_ENABLED" ]]; then
  rm -f "$NGINX_ENABLED" || true
  echo "   Removed enabled symlink: $NGINX_ENABLED"
fi
if [[ -f "$NGINX_AVAILABLE" ]]; then
  rm -f "$NGINX_AVAILABLE" || true
  echo "   Removed available file: $NGINX_AVAILABLE"
fi
# reload nginx if any site removed
if command -v nginx >/dev/null 2>&1; then
  if nginx -t >/dev/null 2>&1; then
    systemctl reload nginx || true
  fi
fi

echo "-> Removing virtual environments (if exist)"
for vdir in "${VENV_DIRS[@]}"; do
  if [[ -d "$vdir" ]]; then
    rm -rf "$vdir"
    echo "   Removed venv: $vdir"
  fi
done

echo "-> Removing cloned repositories (if exist)"
for rdir in "${REPO_DIRS[@]}"; do
  if [[ -d "$rdir" ]]; then
    rm -rf "$rdir"
    echo "   Removed repo dir: $rdir"
  fi
done

echo "-> Handling database files"
if [[ "$KEEP_DB" == "true" ]]; then
  echo "   Keeping DB files (--keep-db)."
else
  for dbf in "${DB_FILES[@]}"; do
    if [[ -f "$dbf" ]]; then
      rm -f "$dbf"
      echo "   Removed DB: $dbf"
    fi
  done
fi

echo "-> Handling TLS certs"
if [[ "$KEEP_CERTS" == "true" ]]; then
  echo "   Keeping certs (--keep-certs)."
else
  if [[ -d "$CERT_DIR" ]]; then
    rm -rf "$CERT_DIR"
    echo "   Removed cert dir: $CERT_DIR"
  fi
fi

echo "-> (Optional) UFW rules cleanup - skipped by default"
echo "   If you had opened 443/80 specifically for this service and want to close:"
echo "     sudo ufw delete allow 443"
echo "     sudo ufw delete allow 80"

echo
echo "Uninstall complete."
echo "You can vacuum old logs if desired:"
echo "  sudo journalctl --unit=${APP_NAME} --since today"
echo "  sudo journalctl --vacuum-time=7d"
