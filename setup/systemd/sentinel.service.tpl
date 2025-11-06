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

# HF/Transformers 캐시(쓰기 경로를 OS 표준 위치로)
Environment=TRANSFORMERS_CACHE=/var/cache/sentinel/hf
Environment=HF_HUB_OFFLINE=1
Environment=TRANSFORMERS_OFFLINE=1
Environment=TOKENIZERS_PARALLELISM=false

# 실행 전 디렉터리 보장
ExecStartPre=/usr/bin/mkdir -p /var/cache/sentinel/hf
ExecStartPre=/usr/bin/chown -R ${RUN_USER}:${RUN_GROUP} /var/cache/sentinel

# 기존 사전 체크
ExecStartPre=/usr/bin/test -x ${APP_DST}/.venv/bin/python3
ExecStartPre=/usr/bin/test -r ${CERT_FULLCHAIN}
ExecStartPre=/usr/bin/test -r ${CERT_PRIVKEY}

# uvicorn 실행(기존)
ExecStart=${APP_DST}/.venv/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port 443 \
  --ssl-certfile ${CERT_FULLCHAIN} \
  --ssl-keyfile  ${CERT_PRIVKEY}

AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
PrivateTmp=true

# 쓰기 허용 경로는 '존재하는 상위'로 잡기
ReadWritePaths=${APP_DST}
ReadWritePaths=/var/cache/sentinel

Restart=always
RestartSec=2
TimeoutStopSec=15
LimitNOFILE=65536
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
