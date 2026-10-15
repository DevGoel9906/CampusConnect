from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Optional
from jose import JWTError, jwt
from fastapi import Cookie, Header, HTTPException
from .config import get_settings


def _settings():
    return get_settings()


def _access_secret() -> str:
    s = _settings().jwt_secret
    if len(s) < 32 and _settings().node_env == "production":
        raise RuntimeError("JWT_SECRET must be at least 32 characters in production")
    return s


def _refresh_secret() -> str:
    s = _settings().jwt_refresh_secret
    if len(s) < 32 and _settings().node_env == "production":
        raise RuntimeError("JWT_REFRESH_SECRET must be at least 32 characters in production")
    return s


def sign_access_token(user_id: str, role: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=_settings().jwt_access_expires_minutes)
    return jwt.encode({"userId": user_id, "role": role, "exp": expires}, _access_secret(), algorithm="HS256")


def sign_refresh_token(user_id: str, role: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(days=_settings().jwt_refresh_expires_days)
    return jwt.encode({"userId": user_id, "role": role, "exp": expires}, _refresh_secret(), algorithm="HS256")


def _decode(token: str, secret: str) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        if not isinstance(payload.get("userId"), str) or payload.get("role") not in ("STUDENT", "ADMIN"):
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token")


def verify_access_token(token: str) -> dict:
    return _decode(token, _access_secret())


def verify_refresh_token(token: str) -> dict:
    return _decode(token, _refresh_secret())


def hash_refresh_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()


# ── FastAPI dependency ───────────────────────────────────────────────────────

def _extract_token(
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None),
) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    return access_token


def get_token_payload(
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None),
) -> dict:
    token = _extract_token(authorization, access_token)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return verify_access_token(token)


def get_optional_token_payload(
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None),
) -> Optional[dict]:
    token = _extract_token(authorization, access_token)
    if not token:
        return None
    try:
        return verify_access_token(token)
    except HTTPException:
        return None
