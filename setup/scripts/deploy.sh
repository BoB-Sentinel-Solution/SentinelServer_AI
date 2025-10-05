#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(dirname "${BASE_DIR}")"

# 실행 권한 부여(최초 1회)
chmod +x "${BASE_DIR}/scripts/"*.sh || true

# .env 로드
if [[ -f "${BASE_DIR}/.env" ]]; then
  set -o allexport
  source "${BASE_DIR}/.env"
  set +o allexport
else
  echo "NOTE: ${BASE_DIR}/.env not found. Using defaults or .env.example values if exported."
fi

echo "[SYS] install base packages"
sudo apt-get update -y
sudo apt-get install -y python3-venv openssl rsync curl

# 방화벽
bash "${BASE_DIR}/scripts/setup_firewall.sh"

# 앱 동기화 + venv + deps (루트 app.py/requirements.txt 사용)
bash "${BASE_DIR}/scripts/sync_app.sh"

# 인증서 (SERVER_IP 자동 감지 보조)
if [[ -z "${SERVER_IP:-}" ]]; then
  echo "WARNING: SERVER_IP not set; auto-detect public IP..."
  SERVER_IP="$(curl -s https://ifconfig.me || true)"
  export SERVER_IP
  echo "Detected SERVER_IP=${SERVER_IP}"
fi
bash "${BASE_DIR}/scripts/generate_self_signed.sh"

# systemd 서비스
bash "${BASE_DIR}/scripts/install_service.sh"

# --- Health check (max 10s, every 1s) ---
echo "[CHECK] waiting for service to become healthy (max 10s)..."
ok=0
for i in {1..10}; do
  resp="$(curl -sk --max-time 1 https://127.0.0.1/healthz || true)"
  if echo "$resp" | grep -q '"ok"\s*:\s*true'; then
    echo "Health OK on attempt $i -> $resp"
    ok=1
    break
  fi
  if sudo ss -ltnp | grep -q ':443'; then
    echo "443 is listening, retrying health... (attempt $i)"
  else
    echo "443 not listening yet (attempt $i)"
  fi
  sleep 1
done

# venv 경로 안내 (APP_DST가 없으면 기본값 사용)
VENV_ACT="${APP_DST:-/home/ubuntu/sentinel}/.venv/bin/activate"

if [ "$ok" -ne 1 ]; then
  echo "Health not ready after 10s"
  echo "Last response: ${resp:-<no response>}"
  journalctl -u sentinel -n 20 --no-pager || true
else
  echo
  echo "[NEXT] 가상환경 활성화:"
  echo "source $VENV_ACT"
  echo "(비활성화: deactivate)"
fi