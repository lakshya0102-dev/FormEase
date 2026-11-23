"""
Security and JWT token verification for Supabase Authentication.
Strictly verifies legacy HS256 JWTs and current RS256/ES256 signing keys.
Rejects any unverified, expired, or malformed tokens.
"""
from typing import Optional, Dict, Any
import uuid
import time
import threading
import logging
import os
import random
import socket
import traceback
import httpx
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.concurrency import run_in_threadpool
from jose import jwt, JWTError, ExpiredSignatureError
from .config import settings

logger = logging.getLogger(__name__)
security_scheme = HTTPBearer(auto_error=False)
_jwks_cache: Dict[str, Any] = {"keys": [], "expires_at": 0.0, "url": ""}
_jwks_lock = threading.Lock()
_jwks_client: Optional[httpx.Client] = None


def _create_jwks_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(connect=2.0, read=5.0, write=2.0, pool=1.0),
        limits=httpx.Limits(
            max_connections=2,
            max_keepalive_connections=1,
            keepalive_expiry=5.0,
        ),
        trust_env=True,
    )


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain = []
    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__
        if current is None and not chain[-1].__suppress_context__:
            current = chain[-1].__context__
    return chain


def _classify_jwks_failure(exc: BaseException) -> tuple[str, Optional[int], Optional[int]]:
    chain = _exception_chain(exc)
    http_error = next((item for item in chain if isinstance(item, httpx.HTTPStatusError)), None)
    if http_error is not None:
        return "http_response", None, http_error.response.status_code
    if any(isinstance(item, httpx.ProxyError) for item in chain):
        return "proxy", None, None
    timeout = next((item for item in chain if isinstance(item, httpx.TimeoutException)), None)
    if timeout is not None:
        return f"timeout_{type(timeout).__name__.lower()}", None, None
    if any(isinstance(item, socket.gaierror) for item in chain):
        return "dns", None, None
    os_error = next((item for item in chain if isinstance(item, OSError)), None)
    if os_error is not None or any(isinstance(item, httpx.ConnectError) for item in chain):
        return "tcp_connect", getattr(os_error, "errno", None), None
    return "http_transport", None, None


def _safe_traceback(exc: BaseException) -> str:
    lines = []
    for item in _exception_chain(exc):
        if item.__traceback__ is not None:
            lines.append("Traceback (most recent call last):\n")
            lines.extend(traceback.format_list(traceback.extract_tb(item.__traceback__)))
        lines.append(f"{type(item).__module__}.{type(item).__qualname__}: <message redacted>\n")
    return "".join(lines)


def _log_jwks_failure(exc: BaseException, attempt: int, will_retry: bool) -> None:
    phase, os_errno, http_status = _classify_jwks_failure(exc)
    proxy_environment = {
        "HTTP_PROXY": bool(os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")),
        "HTTPS_PROXY": bool(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")),
        "ALL_PROXY": bool(os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")),
        "NO_PROXY": bool(os.environ.get("NO_PROXY") or os.environ.get("no_proxy")),
    }
    logger.log(
        logging.WARNING if will_retry else logging.ERROR,
        "Supabase JWKS retrieval failed: phase=%s error_type=%s attempt=%s retry=%s "
        "os_errno=%s http_status=%s trust_env=True proxy_environment=%s\n%s",
        phase,
        type(exc).__name__,
        attempt + 1,
        will_retry,
        os_errno,
        http_status,
        proxy_environment,
        _safe_traceback(exc),
    )


def _discard_jwks_client() -> None:
    global _jwks_client

    client = _jwks_client
    _jwks_client = None
    if client is not None:
        client.close()


def _get_supabase_jwks(force_refresh: bool = False) -> list:
    global _jwks_client

    project_url = settings.SUPABASE_URL.rstrip("/")
    jwks_url = f"{project_url}/auth/v1/.well-known/jwks.json"
    now = time.monotonic()
    if not force_refresh and _jwks_cache["url"] == jwks_url and now < _jwks_cache["expires_at"]:
        return _jwks_cache["keys"]

    with _jwks_lock:
        now = time.monotonic()
        if not force_refresh and _jwks_cache["url"] == jwks_url and now < _jwks_cache["expires_at"]:
            return _jwks_cache["keys"]

        for attempt in range(2):
            try:
                if _jwks_client is None:
                    _jwks_client = _create_jwks_client()
                response = _jwks_client.get(jwks_url)
                response.raise_for_status()
                jwks = response.json()
                keys = jwks.get("keys") if isinstance(jwks, dict) else None
                if not isinstance(keys, list):
                    raise ValueError("Supabase JWKS response has an invalid keys field.")
            except httpx.HTTPStatusError as exc:
                will_retry = exc.response.status_code >= 500 and attempt == 0
                _log_jwks_failure(exc, attempt, will_retry)
                if will_retry:
                    _discard_jwks_client()
                    time.sleep(random.uniform(0.05, 0.15) * (2 ** attempt))
                    continue
                _discard_jwks_client()
                raise
            except (httpx.TransportError, OSError) as exc:
                will_retry = attempt == 0
                _log_jwks_failure(exc, attempt, will_retry)
                if will_retry:
                    _discard_jwks_client()
                    time.sleep(random.uniform(0.05, 0.15) * (2 ** attempt))
                    continue
                _discard_jwks_client()
                raise
            except Exception as exc:
                _log_jwks_failure(exc, attempt, False)
                raise

            _jwks_cache.update({
                "url": jwks_url,
                "keys": keys,
                "expires_at": time.monotonic() + 480,
            })
            return keys

        raise RuntimeError("Supabase JWKS retrieval failed.")

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
            except JWTError:
                raise
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Unable to retrieve Supabase signing keys.",
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
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
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
