[Unit]
Description=Sentinel FastAPI (HTTPS :443 direct)
Wants=network-online.target
After=network-online.target

[Service]
User=${RUN_USER}
WorkingDirectory=${APP_DST}
Environment=PATH=${APP_DST}/.venv/bin
# 사전 검사: python 실행 파일 존재/실행권한 확인
ExecStartPre=/usr/bin/test -x ${APP_DST}/.venv/bin/python3

# 모듈 실행 방식 (shebang/권한 이슈 회피)
ExecStart=${APP_DST}/.venv/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port 443 \
  --ssl-keyfile /etc/ssl/sentinel/privkey.pem \
  --ssl-certfile /etc/ssl/sentinel/fullchain.pem

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
