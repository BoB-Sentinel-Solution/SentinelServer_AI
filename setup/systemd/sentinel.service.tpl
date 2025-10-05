[Unit]
Description=Sentinel FastAPI (HTTPS :443 direct)
Wants=network-online.target
After=network-online.target

[Service]
User=${RUN_USER}
WorkingDirectory=${APP_DST}
Environment=PATH=${APP_DST}/.venv/bin
# Environment=TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

ExecStart=${APP_DST}/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 443 \
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
ProtectHome=true
PrivateTmp=true
ReadWritePaths=${APP_DST}

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
