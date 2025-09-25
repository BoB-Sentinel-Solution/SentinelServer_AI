import os

# --- mTLS ---
USE_MTLS = os.getenv("USE_MTLS", "true").lower() == "true"
TLS_CA_FILE = os.getenv("TLS_CA_FILE", "./certs/ca.pem")
TLS_CERT_FILE = os.getenv("TLS_CERT_FILE", "./certs/server_cert.pem")
TLS_KEY_FILE = os.getenv("TLS_KEY_FILE", "./certs/server_key.pem")

# --- (선택) LLM 보조판별 ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ENABLE_LLM = bool(OPENAI_API_KEY) and os.getenv("ENABLE_LLM", "true").lower() == "true"

# --- 정책 ---
BLOCK_ON_HIGH_RISK = os.getenv("BLOCK_ON_HIGH_RISK", "true").lower() == "true"
HIGH_RISK_THRESHOLD = int(os.getenv("HIGH_RISK_THRESHOLD", "2"))
MAX_MASK_FIELDS = int(os.getenv("MAX_MASK_FIELDS", "5000"))
MAX_SAMPLE_TEXT = int(os.getenv("MAX_SAMPLE_TEXT", "4000"))

# --- (mTLS 사용 시 HMAC 비활성 권장) ---
ENABLE_HMAC = os.getenv("ENABLE_HMAC", "false").lower() == "true"
INSPECT_SHARED_SECRET = os.getenv("INSPECT_SHARED_SECRET", "").strip()
REPLAY_WINDOW_MS = int(os.getenv("REPLAY_WINDOW_MS", "60000"))
