[Unit]
Description=Sentinel FastAPI (HTTPS :443 direct)
Wants=network-online.target
After=network-online.target

[Service]
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${APP_DST}

EnvironmentFile=${APP_DST}/setup/.env
Environment=PATH=${APP_DST}/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=PYTHONUNBUFFERED=1

# HF/Transformers 캐시
Environment=TRANSFORMERS_CACHE=/var/cache/sentinel/hf
Environment=HF_HUB_OFFLINE=1
Environment=TRANSFORMERS_OFFLINE=1
Environment=TOKENIZERS_PARALLELISM=false

# >>> systemd가 /var/cache/sentinel을 선제 생성
CacheDirectory=sentinel
CacheDirectoryMode=0755
# (선택) 하위 hf 디렉토리는 ExecStartPre로 생성해도 되고 런타임에 생성돼도 OK
ExecStartPre=/usr/bin/mkdir -p /var/cache/sentinel/hf
ExecStartPre=/usr/bin/chown -R ${RUN_USER}:${RUN_GROUP} /var/cache/sentinel

# 기존 사전 체크
ExecStartPre=/usr/bin/test -x ${APP_DST}/.venv/bin/python3
ExecStartPre=/usr/bin/test -r ${CERT_FULLCHAIN}
ExecStartPre=/usr/bin/test -r ${CERT_PRIVKEY}

# uvicorn HTTPS
ExecStart=${APP_DST}/.venv/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port 443 \
  --ssl-certfile ${CERT_FULLCHAIN} \
  --ssl-keyfile  ${CERT_PRIVKEY}

AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
PrivateTmp=true
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
