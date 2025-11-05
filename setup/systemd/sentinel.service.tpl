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

[Install]
WantedBy=multi-user.target
