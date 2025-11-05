#!/usr/bin/env bash
set -euo pipefail
# 위치: ~/SentinelServer_AI/setup/scripts/setup_firewall.sh

# 목적: 80/443 허용 (있을 때만). 방화벽이 꺼져있으면 켜지지 않음(보수적).
open_ports() {
  local ports="$1"
  echo "[FW] allow ${ports}"
  ufw allow ${ports} || true
}

if command -v ufw >/dev/null 2>&1; then
  status="$(ufw status 2>/dev/null | head -1 || true)"
  echo "[FW] ufw detected: ${status}"
  open_ports "80/tcp"
  open_ports "443/tcp"
  # ufw가 inactive면 정책만 추가하고 활성화는 하지 않음(운영 정책 보호).
else
  echo "[FW] ufw not found. Skipping. (클라우드 보안그룹/iptables를 별도 확인하세요)"
fi
