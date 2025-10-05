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

# 헬스체크
echo "[CHECK] curl -k https://127.0.0.1/healthz"
curl -k https://127.0.0.1/healthz || true

echo "[DONE] Deployment finished."
echo "Service:    systemctl status sentinel"
echo "Health:     curl -k https://${SERVER_IP:-<YOUR_IP>}/healthz"
