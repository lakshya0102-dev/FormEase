"""
Security and JWT token verification for Supabase Authentication.
Strictly verifies legacy HS256 JWTs and current RS256/ES256 signing keys.
Rejects any unverified, expired, or malformed tokens.
"""
from typing import Optional, Dict, Any
import uuid
import time
import threading
import httpx
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.concurrency import run_in_threadpool
from jose import jwt, JWTError, ExpiredSignatureError
from backend.app.core.config import settings

security_scheme = HTTPBearer(auto_error=False)
_jwks_cache: Dict[str, Any] = {"keys": [], "expires_at": 0.0, "url": ""}
_jwks_lock = threading.Lock()

def _get_supabase_jwks(force_refresh: bool = False) -> list:
    project_url = settings.SUPABASE_URL.rstrip("/")
    jwks_url = f"{project_url}/auth/v1/.well-known/jwks.json"
    now = time.monotonic()
    if not force_refresh and _jwks_cache["url"] == jwks_url and now < _jwks_cache["expires_at"]:
        return _jwks_cache["keys"]

    with _jwks_lock:
        now = time.monotonic()
        if not force_refresh and _jwks_cache["url"] == jwks_url and now < _jwks_cache["expires_at"]:
            return _jwks_cache["keys"]
        response = httpx.get(jwks_url, timeout=5.0)
        response.raise_for_status()
        keys = response.json().get("keys", [])
        if not isinstance(keys, list):
            raise ValueError("Supabase JWKS response has an invalid keys field.")
        _jwks_cache.update({"url": jwks_url, "keys": keys, "expires_at": now + 480})
        return keys

def verify_supabase_jwt(token: str) -> Dict[str, Any]:
    """
    Cryptographically verifies legacy HS256 tokens and Supabase RS256/ES256 tokens.
    Validates token structure, signature, expiration, audience, and asymmetric issuer.
    Never accepts unverified tokens or development bypasses.
    """
    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing or empty.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        decode_options = {"verify_aud": True, "verify_signature": True, "verify_exp": True}

        if algorithm == "HS256":
            if not settings.SUPABASE_JWT_SECRET or settings.SUPABASE_JWT_SECRET == "placeholder-jwt-secret":
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Server configuration error: SUPABASE_JWT_SECRET is not configured.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
                options=decode_options
            )
        elif algorithm in ("ES256", "RS256"):
            key_id = header.get("kid")
            if not key_id:
                raise JWTError("Asymmetric token is missing its key identifier.")
            try:
                keys = _get_supabase_jwks()
                matching_key = next((key for key in keys if key.get("kid") == key_id and key.get("alg", algorithm) == algorithm), None)
                if matching_key is None:
                    keys = _get_supabase_jwks(force_refresh=True)
                    matching_key = next((key for key in keys if key.get("kid") == key_id and key.get("alg", algorithm) == algorithm), None)
                if matching_key is None:
                    raise JWTError("No trusted Supabase signing key matches this token.")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Unable to retrieve Supabase signing keys: {str(e)}",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            payload = jwt.decode(
                token,
                matching_key,
                algorithms=[algorithm],
                audience="authenticated",
                issuer=f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
                options=decode_options
            )
        else:
            raise JWTError("Unsupported Supabase token signing algorithm.")
        return payload
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme)
) -> Dict[str, Any]:
    """
    FastAPI dependency that enforces authentication and returns current user details.
    Guarantees user identity (UUID) is present and verified.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header or Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = await run_in_threadpool(verify_supabase_jwt, credentials.credentials)
    if payload.get("role") != "authenticated":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not belong to an authenticated user.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identity subject (sub).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate that sub is a valid UUID
    try:
        uuid.UUID(str(user_id))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject (sub) is not a valid UUID.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {
        "id": str(user_id),
        "email": payload.get("email", ""),
        "role": payload.get("role", "authenticated"),
        "token": credentials.credentials,
        "raw_payload": payload
    }
