#!/usr/bin/env bash
set -euo pipefail
# 위치: ~/SentinelServer_AI/setup/scripts/sync_app.sh
# 기능:
#  - 레포 → APP_DST 동기화
#  - venv 생성/업데이트, requirements 설치
#  - RUN_USER/RUN_GROUP 권한 보정
#  - --rebuild 옵션: venv 재구축

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

# 코드 동기화 (불필요한 파일 제외)
rsync -av --delete \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude ".venv" \
  "${REPO_ROOT}/" "${APP_DST}/"

chown -R "${RUN_USER}:${RUN_GROUP}" "${APP_DST}"

cd "${APP_DST}"

# venv 처리
if [[ "${REBUILD}" -eq 1 && -d ".venv" ]]; then
  echo "[SYNC] rebuild venv"
  rm -rf .venv
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "[SYNC] create venv"
  python3 -m venv .venv
fi

# 의존성 설치
echo "[SYNC] install requirements"
. .venv/bin/activate
pip install --upgrade pip
if [[ -f requirements.txt ]]; then
  pip install -r requirements.txt
fi
deactivate

# 권한 재확인
chown -R "${RUN_USER}:${RUN_GROUP}" "${APP_DST}"

echo "[SYNC] done"
