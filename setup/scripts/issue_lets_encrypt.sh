#!/usr/bin/env bash
set -euo pipefail

# 위치: ~/SentinelServer_AI/setup/scripts/issue_lets_encrypt.sh

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${BASE_DIR}/.env"

# .env 로드
if [[ -f "${ENV_FILE}" ]]; then
  set -o allexport; source "${ENV_FILE}"; set +o allexport
fi

# 필수/선택 변수
DOMAIN="${DOMAIN:-bobsentinel.com}"
WWW_DOMAIN="${WWW_DOMAIN:-}"            # 비우면 www 없이 발급
EXTRA_DOMAINS="${EXTRA_DOMAINS:-}"      # 예: "sentinel.bobsentinel.com,api.bobsentinel.com"
STAGING="${STAGING:-0}"                 # 1=스테이징(테스트), 0=본발급

echo "[LE] installing certbot (if needed)"
apt-get update -y
apt-get install -y certbot

# 도메인 목록 구성
DOMAINS=(-d "${DOMAIN}")
if [[ -n "${WWW_DOMAIN}" ]]; then
  DOMAINS+=(-d "${WWW_DOMAIN}")
fi
IFS=',' read -r -a _extra <<< "${EXTRA_DOMAINS}"
for d in "${_extra[@]}"; do
  d_trim="$(echo "$d" | xargs)"
  [[ -n "$d_trim" ]] && DOMAINS+=(-d "$d_trim")
done

# 포트 80 확보(standalone 사용하므로 80을 certbot이 점유해야 함)
echo "[LE] stopping sentinel (to free :80)"
systemctl stop sentinel 2>/dev/null || true

# UFW 일시 허용 (있을 경우만)
if command -v ufw >/dev/null 2>&1; then
  UFW_STATUS="$(ufw status | head -n1 || true)"
  if echo "$UFW_STATUS" | grep -qi "Status: active"; then
    echo "[LE] ufw allow 80/tcp (temporary)"
    ufw allow 80/tcp || true
    UFW_TOUCHED=1
  else
    UFW_TOUCHED=0
  fi
else
  UFW_TOUCHED=0
fi

# 스테이징 플래그
STAGING_FLAG=()
if [[ "${STAGING}" == "1" ]]; then
  STAGING_FLAG=(--staging)
  echo "[LE] using STAGING environment"
fi

echo "[LE] issuing for: ${DOMAINS[*]}"
set +e
certbot certonly --standalone "${DOMAINS[@]}" \
  --agree-tos --email "admin@${DOMAIN}" --non-interactive "${STAGING_FLAG[@]}"
RC=$?
set -e

# 갱신 훅: 성공 시 sentinel 자동 재시작
install -d /etc/letsencrypt/renewal-hooks/deploy
cat >/etc/letsencrypt/renewal-hooks/deploy/00-restart-sentinel.sh <<'EOF'
#!/bin/sh
systemctl restart sentinel || true
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/00-restart-sentinel.sh

# UFW 롤백(필요 시)
if [[ "${UFW_TOUCHED}" == "1" ]]; then
  echo "[LE] ufw delete allow 80/tcp"
  ufw delete allow 80/tcp || true
fi

if [[ $RC -ne 0 ]]; then
  echo "[ERR] certbot issuance failed (rc=${RC})"
  echo "      - 동일 식별자 집합 레이트리밋일 수 있습니다."
  echo "      - WWW_DOMAIN 제거 또는 EXTRA_DOMAINS로 새 서브도메인 사용, 혹은 쿨다운 이후 재시도."
  exit $RC
fi

echo "[LE] issued paths:"
LIVE_BASE="/etc/letsencrypt/live/${DOMAIN}"
echo "  ${LIVE_BASE}/fullchain.pem"
echo "  ${LIVE_BASE}/privkey.pem"

# sentinel 재시작은 renewal-hook에 의해 자동 처리되지만, 최초 발급 직후 즉시 반영하려면:
systemctl restart sentinel || true
