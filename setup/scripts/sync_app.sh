#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(dirname "${BASE_DIR}")"

# Load env
if [[ -f "${BASE_DIR}/.env" ]]; then
  set -o allexport
  source "${BASE_DIR}/.env"
  set +o allexport
fi

APP_DST="${APP_DST:-/home/ubuntu/sentinel}"
RUN_USER="${RUN_USER:-ubuntu}"
RUN_GROUP="${RUN_GROUP:-ubuntu}"

echo "[APP] sync -> ${APP_DST}"
sudo install -d -m 755 -o "${RUN_USER}" -g "${RUN_GROUP}" "${APP_DST}"

# 루트의 app.py 배포
sudo install -m 644 -o "${RUN_USER}" -g "${RUN_GROUP}" "${REPO_ROOT}/app.py" "${APP_DST}/app.py"

# 루트의 requirements.txt 배포
if [[ -f "${REPO_ROOT}/requirements.txt" ]]; then
  sudo install -m 644 -o "${RUN_USER}" -g "${RUN_GROUP}" "${REPO_ROOT}/requirements.txt" "${APP_DST}/requirements.txt"
fi

# venv 구성 및 패키지 설치
if [[ ! -d "${APP_DST}/.venv" ]]; then
  echo "[APP] create venv"
  sudo -u "${RUN_USER}" -g "${RUN_GROUP}" bash -c "cd '${APP_DST}' && python3 -m venv .venv"
fi

echo "[APP] install deps"
sudo -u "${RUN_USER}" -g "${RUN_GROUP}" bash -c "source '${APP_DST}/.venv/bin/activate' && pip install --upgrade pip && pip install -r '${APP_DST}/requirements.txt'"

echo "[APP] done."
