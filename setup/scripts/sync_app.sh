#!/usr/bin/env bash
set -euo pipefail
# 위치: ~/SentinelServer_AI/setup/scripts/sync_app.sh
# 기능:
#  - 레포 → APP_DST 동기화
#  - venv 생성/업데이트
#  - PyTorch(CUDA/CPU) 전용 인덱스 먼저 설치 → 나머지 의존성 설치(토치 계열 제외)
#  - RUN_USER/RUN_GROUP 권한 보정
#  - --rebuild 옵션: venv 재구축

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${BASE_DIR}/.." && pwd)"
ENV_FILE="${BASE_DIR}/.env"

# .env 로드 (APP_DST, RUN_USER/GROUP, TORCH_* 등)
if [[ -f "${ENV_FILE}" ]]; then
  set -o allexport; source "${ENV_FILE}"; set +o allexport
fi

RUN_USER="${RUN_USER:-root}"
RUN_GROUP="${RUN_GROUP:-$RUN_USER}"
APP_DST="${APP_DST:-${REPO_ROOT}}"

# PyTorch 설치 정책(환경변수로 오버라이드 가능)
: "${TORCH_CHANNEL:=cu121}"       # cu121 | cpu
: "${TORCH_VERSION:=2.4.1}"
: "${VISION_VERSION:=0.19.1}"
: "${AUDIO_VERSION:=2.4.1}"

REBUILD=0
[[ "${1:-}" == "--rebuild" ]] && REBUILD=1

echo "[SYNC] REPO_ROOT=${REPO_ROOT}"
echo "[SYNC] APP_DST   =${APP_DST}"
echo "[SYNC] RUN_USER  =${RUN_USER}:${RUN_GROUP}"
mkdir -p "${APP_DST}"

# 코드 동기화 (불필요한 파일 제외)
rsync -av --delete \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude ".venv" \
  "${REPO_ROOT}/" "${APP_DST}/"

chown -R "${RUN_USER}:${RUN_GROUP}" "${APP_DST}"
cd "${APP_DST}"

# venv 처리
if [[ "${REBUILD}" -eq 1 && -d ".venv" ]]; then
  echo "[SYNC] rebuild venv"
  rm -rf .venv
fi
if [[ ! -x ".venv/bin/python" ]]; then
  echo "[SYNC] create venv"
  python3 -m venv .venv
fi

# 의존성 설치
echo "[SYNC] install requirements"
. .venv/bin/activate
python -m pip install -U pip setuptools wheel

# ----- PyTorch 스택 먼저(전용 인덱스) -----
if command -v nvidia-smi >/dev/null 2>&1 && [[ "${TORCH_CHANNEL}" != "cpu" ]]; then
  echo "[PYTORCH] installing CUDA ${TORCH_CHANNEL} wheels..."
  pip install --index-url "https://download.pytorch.org/whl/${TORCH_CHANNEL}" \
    "torch==${TORCH_VERSION}" "torchvision==${VISION_VERSION}" "torchaudio==${AUDIO_VERSION}"
else
  echo "[PYTORCH] installing CPU wheels..."
  pip install --index-url "https://download.pytorch.org/whl/cpu" \
    "torch==${TORCH_VERSION}" "torchvision==${VISION_VERSION}" "torchaudio==${AUDIO_VERSION}"
fi

# ----- 나머지 requirements (토치/트리톤/엔비디아 계열 제외) -----
if [[ -f requirements.txt ]]; then
  echo "[PIP] installing app requirements (exclude torch/vision/audio/triton/nvidia-*)"
  # requirements.txt에서 토치 계열/저수준 CUDA 패키지 제거
  grep -Ev '^(torch|torchvision|torchaudio|triton|nvidia-).*$' requirements.txt > /tmp/req.clean.txt || true
  # 비어 있어도 문제 없이 넘어가도록 || true 처리
  if [[ -s /tmp/req.clean.txt ]]; then
    pip install -r /tmp/req.clean.txt
  else
    echo "[PIP] nothing to install from requirements (after filtering)."
  fi
  rm -f /tmp/req.clean.txt
fi

deactivate

# 권한 재확인
chown -R "${RUN_USER}:${RUN_GROUP}" "${APP_DST}"

echo "[SYNC] done"
