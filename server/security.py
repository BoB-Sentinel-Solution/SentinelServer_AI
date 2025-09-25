import time, hmac, hashlib, base64
from .config import ENABLE_HMAC, INSPECT_SHARED_SECRET, REPLAY_WINDOW_MS

def verify_hmac(request_body: bytes, headers: dict) -> bool:
    if not ENABLE_HMAC or not INSPECT_SHARED_SECRET:
        return True  # mTLS가 기본이므로 HMAC 미사용이 기본
    ts = headers.get("x-sign-ts", "")
    nonce = headers.get("x-sign-nonce", "")
    sig = headers.get("x-sign", "")
    try:
        ts_i = int(ts); now = int(time.time()*1000)
        if abs(now - ts_i) > REPLAY_WINDOW_MS:
            return False
        msg = (ts + "|" + nonce + "|").encode("utf-8") + request_body
        calc = base64.b64encode(hmac.new(INSPECT_SHARED_SECRET.encode(), msg, hashlib.sha256).digest()).decode()
        return hmac.compare_digest(calc, sig)
    except Exception:
        return False
