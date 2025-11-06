#!/usr/bin/env bash
set -euo pipefail
# 위치: setup/scripts/sync_app.sh

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${BASE_DIR}/.." && pwd)"
ENV_FILE="${BASE_DIR}/.env"

# .env 로드
if [[ -f "${ENV_FILE}" ]]; then
  set -o allexport; source "${ENV_FILE}"; set +o allexport
fi

RUN_USER="${RUN_USER:-root}"
RUN_GROUP="${RUN_GROUP:-$RUN_USER}"
APP_DST="${APP_DST:-${REPO_ROOT}}"

REBUILD=0
[[ "${1:-}" == "--rebuild" ]] && REBUILD=1

echo "[SYNC] REPO_ROOT=${REPO_ROOT}"
echo "[SYNC] APP_DST   =${APP_DST}"
echo "[SYNC] RUN_USER  =${RUN_USER}:${RUN_GROUP}"
mkdir -p "${APP_DST}"

rsync -av --delete \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude ".venv" \
  "${REPO_ROOT}/" "${APP_DST}/"

chown -R "${RUN_USER}:${RUN_GROUP}" "${APP_DST}"
cd "${APP_DST}"

if [[ "${REBUILD}" -eq 1 && -d ".venv" ]]; then
  echo "[SYNC] rebuild venv"
  rm -rf .venv
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "[SYNC] create venv"
  python3 -m venv .venv
fi

echo "[SYNC] install requirements"
. .venv/bin/activate
pip install --upgrade pip wheel
# PyTorch/cu121은 이미 설치되어 있다면 스킵됨. 없으면 다음 줄 유지(옵션):
# pip install --index-url https://download.pytorch.org/whl/cu121 torch==2.4.1+cu121 torchvision==0.19.1+cu121 torchaudio==2.4.1+cu121

# accelerate (AI 부팅시 요구), uvicorn 등 보강
pip install --upgrade accelerate "uvicorn[standard]" psutil

if [[ -f requirements.txt ]]; then
  pip install -r requirements.txt
fi
deactivate

chown -R "${RUN_USER}:${RUN_GROUP}" "${APP_DST}"
echo "[SYNC] done"
