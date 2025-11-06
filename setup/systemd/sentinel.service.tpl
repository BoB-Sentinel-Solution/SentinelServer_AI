[Unit]
Description=Sentinel FastAPI (HTTPS :443 direct)
Wants=network-online.target
After=network-online.target

[Service]
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${APP_DST}

EnvironmentFile=${APP_DST}/setup/.env
Environment=PATH=${APP_DST}/.venv/bin
Environment=PYTHONUNBUFFERED=1
SyslogIdentifier=sentinel
UMask=027

# 사전 검사: venv 파이썬/인증서 존재 확인
ExecStartPre=/usr/bin/test -x ${APP_DST}/.venv/bin/python3
ExecStartPre=/usr/bin/test -r ${CERT_FULLCHAIN}
ExecStartPre=/usr/bin/test -r ${CERT_PRIVKEY}

# Uvicorn 직접 HTTPS 종단
ExecStart=${APP_DST}/.venv/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port 443 \
  --ssl-certfile ${CERT_FULLCHAIN} \
  --ssl-keyfile  ${CERT_PRIVKEY}

AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true

Restart=always
RestartSec=2
TimeoutStopSec=15
LimitNOFILE=65536

ProtectSystem=full
ProtectHome=read-only
PrivateTmp=true
ReadWritePaths=${APP_DST}

StandardOutput=journal
StandardError=journal

# === HF/Transformers 캐시 디렉터리 준비 (쓰기 가능 경로) ===
# ProtectHome=read-only라 /root/.cache 사용 불가 → /var/cache/sentinel/hf 사용
ExecStartPre=/usr/bin/mkdir -p /var/cache/sentinel/hf
ExecStartPre=/usr/bin/chown ${RUN_USER}:${RUN_GROUP} /var/cache/sentinel/hf

# === 런타임 환경변수 (캐시/오프라인/GPU 고정/성능) ===
Environment=TRANSFORMERS_CACHE=/var/cache/sentinel/hf
Environment=HF_HUB_OFFLINE=1
Environment=TRANSFORMERS_OFFLINE=1
Environment=TOKENIZERS_PARALLELISM=false
Environment=CUDA_VISIBLE_DEVICES=0
Environment=PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# === systemd 샌드박스에서 쓰기 허용 경로 추가 ===
ReadWritePaths=${APP_DST}
ReadWritePaths=/var/cache/sentinel/hf

[Install]
WantedBy=multi-user.target
