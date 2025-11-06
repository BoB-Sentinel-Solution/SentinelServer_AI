#!/usr/bin/env bash
set -euo pipefail

# 위치: ~/SentinelServer_AI/setup/scripts/issue_lets_encrypt.sh

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${BASE_DIR}/.env"

# .env 로드
if [[ -f "${ENV_FILE}" ]]; then
  set -o allexport; source "${ENV_FILE}"; set +o allexport
fi

DOMAIN="${DOMAIN:-bobsentinel.com}"
WWW_DOMAIN="${WWW_DOMAIN:-www.bobsentinel.com}"

echo "[LE] installing certbot (if needed)"
apt-get update -y
apt-get install -y certbot

echo "[LE] stopping sentinel if running (free port 80)"
systemctl stop sentinel 2>/dev/null || true

echo "[LE] issuing certificate for ${DOMAIN}, ${WWW_DOMAIN}"
certbot certonly --standalone \
  -d "${DOMAIN}" -d "${WWW_DOMAIN}" \
  --agree-tos --email "admin@${DOMAIN}" --non-interactive

# 갱신 훅(성공/갱신 시 서비스 자동 재시작)
install -d /etc/letsencrypt/renewal-hooks/deploy
cat >/etc/letsencrypt/renewal-hooks/deploy/00-restart-sentinel.sh <<'EOF'
#!/bin/sh
systemctl restart sentinel || true
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/00-restart-sentinel.sh

# 결과 경로 안내
echo "[LE] issued:"
echo "  /etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
echo "  /etc/letsencrypt/live/${DOMAIN}/privkey.pem"
