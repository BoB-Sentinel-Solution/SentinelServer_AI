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

# HF/Transformers 캐시(권장 변수) 및 오프라인
Environment=HF_HOME=/var/cache/sentinel/hf
Environment=HF_HUB_OFFLINE=1
Environment=TRANSFORMERS_OFFLINE=1
Environment=TOKENIZERS_PARALLELISM=false

# 사전 체크 (인증서/venv)
ExecStartPre=/usr/bin/test -x ${APP_DST}/.venv/bin/python3
ExecStartPre=/usr/bin/test -r ${CERT_FULLCHAIN}
ExecStartPre=/usr/bin/test -r ${CERT_PRIVKEY}

# Uvicorn HTTPS 종단
ExecStart=${APP_DST}/.venv/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port 443 \
  --ssl-certfile ${CERT_FULLCHAIN} \
  --ssl-keyfile  ${CERT_PRIVKEY}

AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true

# systemd 보호/샌드박싱
ProtectSystem=full
ProtectHome=read-only
PrivateTmp=true

# ReadWritePaths는 '존재하는 상위'를 포함해야 함
ReadWritePaths=${APP_DST}
ReadWritePaths=/var/cache
ReadWritePaths=/var/cache/sentinel
ReadWritePaths=/var/cache/sentinel/hf

Restart=always
RestartSec=2
TimeoutStopSec=15
LimitNOFILE=65536

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
