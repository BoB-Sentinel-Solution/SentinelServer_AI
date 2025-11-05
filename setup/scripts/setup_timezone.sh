#!/usr/bin/env bash
set -euo pipefail
# 위치: ~/SentinelServer_AI/setup/scripts/setup_timezone.sh

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${BASE_DIR}/.env"

# .env 로드 (없으면 기본 Asia/Seoul)
if [[ -f "${ENV_FILE}" ]]; then
  set -o allexport; source "${ENV_FILE}"; set +o allexport
fi
TZ_NAME="${TZ_NAME:-Asia/Seoul}"

current_tz="$(timedatectl show -p Timezone --value 2>/dev/null || echo '')"
if [[ "$current_tz" != "$TZ_NAME" ]]; then
  echo "[TZ] set timezone -> ${TZ_NAME}"
  timedatectl set-timezone "${TZ_NAME}" || {
    echo "[WARN] timedatectl unavailable. /etc/timezone fallback."
    echo "${TZ_NAME}" >/etc/timezone
    ln -sf "/usr/share/zoneinfo/${TZ_NAME}" /etc/localtime
  }
else
  echo "[TZ] already ${TZ_NAME}"
fi
