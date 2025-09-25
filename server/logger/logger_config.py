# -*- coding: utf-8 -*-
import os
from datetime import timedelta, timezone

# DB
LOG_DATABASE_URL = os.getenv("LOG_DATABASE_URL", "sqlite+aiosqlite:///./logs.db")

# 미리보기/헤더 크기 제한
MAX_HEADERS_LEN = int(os.getenv("MAX_HEADERS_LEN", "32000"))
MAX_PREVIEW_BYTES = int(os.getenv("MAX_PREVIEW_BYTES", "1024"))

# 타임존
KST = timezone(timedelta(hours=9))

# mTLS (uvicorn 직접 mTLS 구동 시 사용)
USE_MTLS = os.getenv("USE_MTLS", "true").lower() == "true"
TLS_CA_FILE = os.getenv("TLS_CA_FILE", "./certs/ca.pem")
TLS_CERT_FILE = os.getenv("TLS_CERT_FILE", "./certs/server_cert.pem")
TLS_KEY_FILE = os.getenv("TLS_KEY_FILE", "./certs/server_key.pem")
