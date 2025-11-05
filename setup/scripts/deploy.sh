#!/usr/bin/env bash
set -euo pipefail

# 위치: ~/SentinelServer_AI/setup/scripts/deploy.sh

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${BASE_DIR}/.." && pwd)"
ENV_FILE="${BASE_DIR}/.env"

# 실행 권한
chmod +x "${BASE_DIR}/scripts/"*.sh 2>/dev/null || true

# .env 로드
if [[ -f "${ENV_FILE}" ]]; then
  set -o allexport; source "${ENV_FILE}"; set +o allexport
else
  echo "NOTE: ${ENV_FILE} not found. Using defaults."
fi

# 기본값
DOMAIN="${DOMAIN:-bobsentinel.com}"
WWW_DOMAIN="${WWW_DOMAIN:-www.bobsentinel.com}"
APP_DST="${APP_DST:-${REPO_ROOT}}"
TZ_NAME="${TZ_NAME:-Asia/Seoul}"

echo "[CONF] DOMAIN=${DOMAIN}, WWW_DOMAIN=${WWW_DOMAIN}, APP_DST=${APP_DST}, TZ=${TZ_NAME}"

echo "[SYS] base packages"
apt-get update -y
apt-get install -y python3-venv python3-pip rsync curl openssl certbot gettext-base

# 타임존/방화벽 유지 호출 (있을 때만)
[[ -x "${BASE_DIR}/scripts/setup_timezone.sh" ]]  && bash "${BASE_DIR}/scripts/setup_timezone.sh"  || timedatectl set-timezone "${TZ_NAME}" || true
[[ -x "${BASE_DIR}/scripts/setup_firewall.sh" ]] && bash "${BASE_DIR}/scripts/setup_firewall.sh" || { command -v ufw >/dev/null 2>&1 && ufw allow 80,443/tcp || true; }

# 앱 동기화 + venv (기존 로직 유지)
if [[ -x "${BASE_DIR}/scripts/sync_app.sh" ]]; then
  bash "${BASE_DIR}/scripts/sync_app.sh"
else
  echo "[APP] sync to ${APP_DST}"
  mkdir -p "${APP_DST}"
  rsync -av --delete --exclude ".git" --exclude "__pycache__" --exclude ".venv" "${REPO_ROOT}/" "${APP_DST}/"
  cd "${APP_DST}"
  python3 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  [[ -f requirements.txt ]] && pip install -r requirements.txt
  deactivate
fi

# (1) self-signed 생성(초기 가동용/백업용) — 기존 호출 유지
bash "${BASE_DIR}/scripts/generate_self_signed.sh"

# (2) Let's Encrypt 자동 발급 — 실패해도 self-signed로 우선 가동되도록 시도
set +e
bash "${BASE_DIR}/scripts/issue_lets_encrypt.sh"
LE_STATUS=$?
set -e
if [[ "${LE_STATUS}" -ne 0 ]]; then
  echo "[WARN] Let's Encrypt issuance failed. Will continue with self-signed for now."
fi

# (3) 서비스 설치/재시작 — install_service가 LE 우선/없으면 self-signed 사용
bash "${BASE_DIR}/scripts/install_service.sh"

# (4) 헬스체크(최대 10초)
echo "[CHECK] waiting for health (max 10s)"
ok=0
resp=""
for i in $(seq 1 10); do
  resp="$(curl -sk --max-time 1 https://127.0.0.1/healthz || true)"
  if echo "$resp" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
    echo "Health OK at try $i -> $resp"
    ok=1; break
  fi
  if ss -ltnp | grep -q ':443'; then
    echo "443 listening, retry... ($i)"
  else
    echo "443 not listening yet ($i)"
  fi
  sleep 1
done

VENV_ACT="${APP_DST}/.venv/bin/activate"
if [[ "$ok" -ne 1 ]]; then
  echo "[ERR] Health not ready after 10s"
  echo "Last response: ${resp:-<no response>}"
  journalctl -u sentinel -n 50 --no-pager || true
else
  echo
  echo "[Guide] venv: source ${VENV_ACT}"
  echo "[Guide] log : journalctl -u sentinel -n 100 -f"
fi

echo "[DONE] Deploy finished."
echo "Service:   systemctl status sentinel"
echo "Dashboard: curl -I https://${DOMAIN}/dashboard/"
echo "Cert info: echo | openssl s_client -connect ${DOMAIN}:443 -servername ${DOMAIN} 2>/dev/null | openssl x509 -noout -issuer -subject -dates"
