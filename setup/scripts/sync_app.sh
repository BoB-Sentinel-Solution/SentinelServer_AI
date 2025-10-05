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

echo "[APP] target -> ${APP_DST}"
sudo install -d -m 755 -o "${RUN_USER}" -g "${RUN_GROUP}" "${APP_DST}"

# 레포 루트와 배포 경로가 같은 경우 파일 복사 스킵
if [[ "$(realpath "${REPO_ROOT}")" == "$(realpath "${APP_DST}")" ]]; then
  echo "[APP] REPO_ROOT == APP_DST (same directory). Skip file copy."
else
  echo "[APP] syncing files to ${APP_DST}"
  # app.py
  sudo install -m 644 -o "${RUN_USER}" -g "${RUN_GROUP}" "${REPO_ROOT}/app.py" "${APP_DST}/app.py"
  # requirements.txt
  if [[ -f "${REPO_ROOT}/requirements.txt" ]]; then
    sudo install -m 644 -o "${RUN_USER}" -g "${RUN_GROUP}" "${REPO_ROOT}/requirements.txt" "${APP_DST}/requirements.txt"
  fi
fi

# venv 생성 (없으면 생성)
if [[ ! -x "${APP_DST}/.venv/bin/python" ]]; then
  echo "[APP] creating venv..."
  sudo -u "${RUN_USER}" -g "${RUN_GROUP}" bash -c "cd '${APP_DST}' && python3 -m venv .venv"
fi

# 패키지 설치/업데이트 (항상 수행)
echo "[APP] installing deps..."
sudo -u "${RUN_USER}" -g "${RUN_GROUP}" bash -c "source '${APP_DST}/.venv/bin/activate' && \
  pip install --upgrade pip && \
  pip install -r '${APP_DST}/requirements.txt'"

echo "[APP] done."
