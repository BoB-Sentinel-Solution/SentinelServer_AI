#!/usr/bin/env bash
set -euo pipefail

# 위치: ~/SentinelServer_AI/setup/scripts/install_service.sh

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${BASE_DIR}/.." && pwd)"
ENV_FILE="${BASE_DIR}/.env"
TPL="${REPO_ROOT}/setup/systemd/sentinel.service.tpl"
UNIT="/etc/systemd/system/sentinel.service"

# .env 로드
if [[ -f "${ENV_FILE}" ]]; then
  set -o allexport; source "${ENV_FILE}"; set +o allexport
fi

RUN_USER="${RUN_USER:-root}"
RUN_GROUP="${RUN_GROUP:-${RUN_USER}}"
APP_DST="${APP_DST:-${REPO_ROOT}}"
DOMAIN="${DOMAIN:-bobsentinel.com}"

# 인증서 경로 결정 (LE 우선, 없으면 self-signed)
LE_FULLCHAIN="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
LE_PRIVKEY="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"
SS_FULLCHAIN="/etc/ssl/sentinel/fullchain.pem"
SS_PRIVKEY="/etc/ssl/sentinel/privkey.pem"

if [[ -r "${LE_FULLCHAIN}" && -r "${LE_PRIVKEY}" ]]; then
  CERT_FULLCHAIN="${LE_FULLCHAIN}"
  CERT_PRIVKEY="${LE_PRIVKEY}"
  echo "[CERT] using Let's Encrypt certs"
elif [[ -r "${SS_FULLCHAIN}" && -r "${SS_PRIVKEY}" ]]; then
  CERT_FULLCHAIN="${SS_FULLCHAIN}"
  CERT_PRIVKEY="${SS_PRIVKEY}"
  echo "[CERT] using self-signed certs"
else
  echo "[ERROR] No certificate found. Run issue_lets_encrypt.sh or generate_self_signed.sh first."
  exit 1
fi

export RUN_USER RUN_GROUP APP_DST DOMAIN CERT_FULLCHAIN CERT_PRIVKEY

# 템플릿 → 유닛 생성
echo "[UNIT] rendering ${UNIT}"
envsubst < "${TPL}" > "${UNIT}"

systemctl daemon-reload
systemctl enable sentinel
systemctl restart sentinel
systemctl status --no-pager sentinel || true
