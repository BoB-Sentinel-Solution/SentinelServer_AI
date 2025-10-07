#!/usr/bin/env bash
set -euo pipefail

# 기본값: Asia/Seoul (setup/.env에서 덮어씀)
TZ_NAME="${TZ_NAME:-Asia/Seoul}"

# 현재 설정된 타임존과 비교
CURRENT_TZ="$(timedatectl show -p Timezone --value 2>/dev/null || true)"

if [[ "$CURRENT_TZ" != "$TZ_NAME" ]]; then
  echo "[SYS] setting timezone to $TZ_NAME"
  # tzdata 설치 (비대화 모드)
  if ! dpkg -s tzdata >/dev/null 2>&1; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get update -y
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y tzdata
  fi
  # /etc/localtime 심볼릭 링크 설정 및 /etc/timezone 기록
  sudo ln -sf "/usr/share/zoneinfo/$TZ_NAME" /etc/localtime
  echo "$TZ_NAME" | sudo tee /etc/timezone >/dev/null
  sudo dpkg-reconfigure -f noninteractive tzdata || true
else
  echo "[SYS] timezone already $TZ_NAME"
fi

echo "[SYS] current time: $(date -R)"
