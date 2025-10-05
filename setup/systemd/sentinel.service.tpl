[Unit]
Description=Sentinel FastAPI (HTTPS :443 direct)
Wants=network-online.target
After=network-online.target

[Service]
User=${RUN_USER}
WorkingDirectory=${APP_DST}
Environment=PATH=${APP_DST}/.venv/bin
# Environment=TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

# ✅ 모듈 실행로 변경 (스크립트 shebang/권한 문제 회피)
ExecStart=${APP_DST}/.venv/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port 443 \
  --ssl-keyfile /etc/ssl/sentinel/privkey.pem \
  --ssl-certfile /etc/ssl/sentinel/fullchain.pem

# 1024 이하 포트 바인딩 권한
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true

Restart=always
RestartSec=2
TimeoutStopSec=15
LimitNOFILE=65536

# 보안 하드닝
ProtectSystem=full
ProtectHome=true
PrivateTmp=true
ReadWritePaths=${APP_DST}

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
