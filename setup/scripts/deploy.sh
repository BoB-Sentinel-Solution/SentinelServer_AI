#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${BASE_DIR}/.." && pwd)"
ENV_FILE="${BASE_DIR}/.env"

# .env 로드
if [[ -f "${ENV_FILE}" ]]; then
  set -o allexport; source "${ENV_FILE}"; set +o allexport
else
  echo "[ERR] ${ENV_FILE} not found"
  exit 1
fi

RUN_USER="${RUN_USER:-root}"
RUN_GROUP="${RUN_GROUP:-$RUN_USER}"
APP_DST="${APP_DST:-${REPO_ROOT}}"

CERT_BASE="/etc/ssl/sentinel"
CERT_FULLCHAIN="${CERT_BASE}/fullchain.pem"
CERT_PRIVKEY="${CERT_BASE}/privkey.pem"

# ---------------------------
# 캐시 디렉터리(샌드박싱용) '먼저' 생성 (systemd 시작 전)
# ---------------------------
echo "[CACHE] prepare /var/cache/sentinel/hf"
mkdir -p /var/cache/sentinel/hf
chown -R "${RUN_USER}:${RUN_GROUP}" /var/cache/sentinel
chmod 0755 /var/cache/sentinel
chmod 0755 /var/cache/sentinel/hf

# ---------------------------
# 인증서
# ---------------------------
mkdir -p "${CERT_BASE}"

if [[ -n "${DOMAIN:-}" && -n "${WWW_DOMAIN:-}" ]]; then
  echo "[LE] issuing certificate for ${DOMAIN}, ${WWW_DOMAIN}"
  if ! certbot certonly --standalone -d "${DOMAIN}" -d "${WWW_DOMAIN}" --non-interactive --agree-tos -m admin@"${DOMAIN}" --keep-until-expiring; then
    echo "[WARN] Let's Encrypt issuance failed. Will continue with self-signed for now."
    openssl req -x509 -newkey rsa:2048 -nodes -keyout "${CERT_PRIVKEY}" -out "${CERT_FULLCHAIN}" -subj "/CN=${DOMAIN}" -days 365
  else
    ln -sf "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" "${CERT_FULLCHAIN}"
    ln -sf "/etc/letsencrypt/live/${DOMAIN}/privkey.pem"   "${CERT_PRIVKEY}"
  fi
elif [[ -n "${SERVER_IP:-}" ]]; then
  echo "[CERT] self-signed for IP ${SERVER_IP}"
  openssl req -x509 -newkey rsa:2048 -nodes -keyout "${CERT_PRIVKEY}" -out "${CERT_FULLCHAIN}" -subj "/CN=${SERVER_IP}" -days 365
else
  echo "[CERT] self-signed for localhost"
  openssl req -x509 -newkey rsa:2048 -nodes -keyout "${CERT_PRIVKEY}" -out "${CERT_FULLCHAIN}" -subj "/CN=localhost" -days 365
fi

# ---------------------------
# 앱 동기화 + venv
# ---------------------------
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

# ---------------------------
# systemd unit 렌더/반영
# ---------------------------
python3 "${BASE_DIR}/scripts/render_unit.py" \
  --template "${BASE_DIR}/systemd/sentinel.service.tpl" \
  --output   "/etc/systemd/system/sentinel.service" \
  --var "RUN_USER=${RUN_USER}" \
  --var "RUN_GROUP=${RUN_GROUP}" \
  --var "APP_DST=${APP_DST}" \
  --var "CERT_FULLCHAIN=${CERT_FULLCHAIN}" \
  --var "CERT_PRIVKEY=${CERT_PRIVKEY}"

systemctl daemon-reload
systemctl enable sentinel.service || true
systemctl restart sentinel.service

# ---------------------------
# 헬스 체크 (/api/healthz)
# ---------------------------
echo "[CHECK] waiting for health (max 10s)"
for i in {1..10}; do
  sleep 1
  if timeout 1 bash -lc "echo > /dev/tcp/127.0.0.1/443" 2>/dev/null; then
    # allow a beat to uvicorn
    sleep 1
    if curl -ksf https://127.0.0.1/api/healthz >/dev/null; then
      echo "[OK] health ready"
      exit 0
    else
      echo "443 listening, retry... (${i})"
    fi
  else
    echo "443 not listening yet (${i})"
  fi
done

echo "[ERR] Health not ready after 10s"
echo "Last response: $(curl -ks https://127.0.0.1/api/healthz || echo '<no response>')"

echo "[DONE] Deploy finished."
echo "Service:   systemctl status sentinel"
echo "Dashboard: curl -I https://bobsentinel.com/dashboard/"
echo "Cert info: echo | openssl s_client -connect bobsentinel.com:443 -servername bobsentinel.com 2>/dev/null | openssl x509 -noout -issuer -subject -dates"
