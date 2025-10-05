#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(dirname "${BASE_DIR}")"
TPL="${BASE_DIR}/systemd/sentinel.service.tpl"
UNIT="/etc/systemd/system/sentinel.service"

# Load env
if [[ -f "${BASE_DIR}/.env" ]]; then
  set -o allexport
  source "${BASE_DIR}/.env"
  set +o allexport
fi

APP_DST="${APP_DST:-/home/ubuntu/sentinel}"
RUN_USER="${RUN_USER:-ubuntu}"
RUN_GROUP="${RUN_GROUP:-ubuntu}"

echo "[systemd] install -> ${UNIT}"
sudo bash -c "sed \
  -e 's|\${APP_DST}|${APP_DST}|g' \
  -e 's|\${RUN_USER}|${RUN_USER}|g' \
  -e 's|\${RUN_GROUP}|${RUN_GROUP}|g' \
  < '${TPL}' > '${UNIT}'"

sudo systemctl daemon-reload
sudo systemctl enable --now sentinel
sudo systemctl restart sentinel || true
sudo systemctl status --no-pager sentinel || true
