"""SnapEdit Studio auth layer.

- WebUI: admin password -> HMAC-signed session cookie (HttpOnly).
- API:   Bearer token(s) from API_TOKENS / API_TOKEN env (OpenAI-compatible).
No new dependencies: stdlib only.
"""
from __future__ import annotations
import os, time, hmac, hashlib, secrets
from typing import Optional
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

SESSION_COOKIE = "snapedit_session"
SESSION_TTL = int(os.getenv("SESSION_TTL", str(7 * 24 * 3600)))  # 7 days

# --- configuration (env overrides) ---
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "SnapEdit@2026")
_tokens = [t.strip() for t in os.getenv("API_TOKENS", "").split(",") if t.strip()]
if not _tokens:
    _tokens = [os.getenv("API_TOKEN", "snapedit-demo-token-2026")]
API_TOKENS = _tokens
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_hex(32))

# --- session cookie (HMAC signed, tamper-proof) ---
def _sign(payload: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()

def issue_session() -> str:
    exp = int(time.time()) + SESSION_TTL
    return f"{exp}.{_sign(str(exp))}"

def valid_session(token: Optional[str]) -> bool:
    if not token:
        return False
    try:
        exp_s, sig = token.split(".", 1)
        exp = int(exp_s)
    except Exception:
        return False
    if exp < time.time():
        return False
    return hmac.compare_digest(sig, _sign(exp_s))

# --- bearer token ---
def _bearer_ok(authorization: Optional[str]) -> bool:
    if not authorization or not authorization.lower().startswith("bearer "):
        return False
    tok = authorization[7:].strip()
    return any(hmac.compare_digest(tok, t) for t in API_TOKENS)

# --- FastAPI middleware / dependency ---
async def auth_middleware(request: Request, call_next):
    """Protect every /v1/* endpoint: accept Bearer token OR valid session cookie."""
    path = request.url.path
    if path.startswith("/v1/"):
        if not (_bearer_ok(request.headers.get("Authorization")) or valid_session(request.cookies.get(SESSION_COOKIE))):
            return JSONResponse({"detail": "unauthorized: missing or invalid credentials"}, status_code=401)
    return await call_next(request)

def set_session_cookie(resp, value: str, ttl: int = SESSION_TTL) -> None:
    resp.set_cookie(SESSION_COOKIE, value, httponly=True, samesite="lax", max_age=ttl, path="/")

def clear_session_cookie(resp) -> None:
    resp.delete_cookie(SESSION_COOKIE, path="/")
