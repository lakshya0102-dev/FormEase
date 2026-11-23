"""
Security and JWT token verification for Supabase Authentication.
Strictly verifies legacy HS256 JWTs and current RS256/ES256 signing keys.
Rejects any unverified, expired, or malformed tokens.
"""
from typing import Optional, Dict, Any
import uuid
import time
import asyncio
import threading
import logging
import os
import random
import socket
import traceback
import ssl
import queue
from collections import deque
from urllib.parse import urlsplit
import aiohttp
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
_jwks_diagnostic_lock = threading.Lock()
_jwks_diagnostic_started = False
_JWKS_ASYNC_FETCH_TIMEOUT_SECONDS = 7.0


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


async def _fetch_supabase_jwks_async(jwks_url: str) -> list:
    logger.warning("JWKS_ASYNC_RESOLVER_INIT_START")
    connector = aiohttp.TCPConnector(
        resolver=aiohttp.AsyncResolver(timeout=1.0, tries=2),
        limit=1,
        ttl_dns_cache=300,
    )
    timeout = aiohttp.ClientTimeout(total=3.0, connect=2.0, sock_read=2.0)
    trace_config = aiohttp.TraceConfig()

    async def on_dns_start(_session, _context, _params):
        logger.warning("JWKS_ASYNC_DNS_START")

    async def on_dns_end(_session, _context, _params):
        logger.warning("JWKS_ASYNC_DNS_COMPLETE")

    async def on_connection_start(_session, _context, _params):
        logger.warning("JWKS_ASYNC_TCP_CONNECT_START")

    async def on_connection_end(_session, _context, _params):
        logger.warning("JWKS_ASYNC_TCP_CONNECT_COMPLETE")

    trace_config.on_dns_resolvehost_start.append(on_dns_start)
    trace_config.on_dns_resolvehost_end.append(on_dns_end)
    trace_config.on_connection_create_start.append(on_connection_start)
    trace_config.on_connection_create_end.append(on_connection_end)
    logger.warning("JWKS_ASYNC_RESOLVER_INIT_COMPLETE")
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        trust_env=True,
        trace_configs=[trace_config],
    ) as client:
        for attempt in range(2):
            logger.warning("JWKS_ASYNC_HTTP_REQUEST_START attempt=%s", attempt + 1)
            try:
                async with client.get(jwks_url, allow_redirects=False) as response:
                    response.raise_for_status()
                    if response.status != 200:
                        raise ValueError("Supabase JWKS endpoint returned a non-200 response.")
                    jwks = await response.json()
                keys = jwks.get("keys") if isinstance(jwks, dict) else None
                if not isinstance(keys, list):
                    raise ValueError("Supabase JWKS response has an invalid keys field.")
                logger.warning("JWKS_ASYNC_HTTP_RESPONSE_VALID")
                return keys
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
                if attempt == 1:
                    raise
                await asyncio.sleep(random.uniform(0.05, 0.15))
            except aiohttp.ClientResponseError as exc:
                if exc.status < 500 or attempt == 1:
                    raise
                await asyncio.sleep(random.uniform(0.05, 0.15))

    raise RuntimeError("Supabase JWKS async resolver retry limit exceeded.")


def _fetch_supabase_jwks_with_async_resolver(jwks_url: str) -> list:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(asyncio.wait_for(
            _fetch_supabase_jwks_async(jwks_url),
            timeout=_JWKS_ASYNC_FETCH_TIMEOUT_SECONDS,
        ))
    raise RuntimeError("Async JWKS fallback cannot run inside an active event loop.")


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain = []
    seen = set()
    pending = deque([exc])
    while pending:
        current = pending.popleft()
        if id(current) in seen:
            continue
        seen.add(id(current))
        chain.append(current)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return chain


def _os_error_details(exc: BaseException) -> list[dict[str, Any]]:
    chain = _exception_chain(exc)
    errors = []
    for item in chain:
        if not isinstance(item, OSError):
            continue
        canonical_strerror = None
        if isinstance(item.errno, int):
            try:
                canonical_strerror = os.strerror(item.errno)
            except (OverflowError, ValueError):
                pass
        errors.append({
            "exception_class": type(item).__name__,
            "errno": item.errno,
            "strerror": canonical_strerror if item.strerror == canonical_strerror else "<redacted>",
        })
    return errors


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
    if os_error is not None:
        return "tcp_connect", os_error.errno, None
    if any(isinstance(item, httpx.ConnectError) for item in chain):
        return "tcp_connect", None, None
    return "http_transport", None, None


def _jwks_failure_details(exc: BaseException) -> dict[str, Any]:
    phase, os_errno, http_status = _classify_jwks_failure(exc)
    return {
        "phase": phase,
        "exception_class": type(exc).__name__,
        "os_errno": os_errno,
        "os_errors": _os_error_details(exc),
        "http_status": http_status,
    }


def _safe_traceback(exc: BaseException) -> str:
    lines = []
    for item in _exception_chain(exc):
        if item.__traceback__ is not None:
            lines.append("Traceback (most recent call last):\n")
            for frame in traceback.extract_tb(item.__traceback__):
                lines.append(f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}\n')
        lines.append(f"{type(item).__module__}.{type(item).__qualname__}: <message redacted>\n")
    return "".join(lines)


def _log_jwks_failure(exc: BaseException, attempt: int, will_retry: bool) -> None:
    details = _jwks_failure_details(exc)
    proxy_environment = {
        "HTTP_PROXY": bool(os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")),
        "HTTPS_PROXY": bool(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")),
        "ALL_PROXY": bool(os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")),
        "NO_PROXY": bool(os.environ.get("NO_PROXY") or os.environ.get("no_proxy")),
    }
    logger.log(
        logging.WARNING if will_retry else logging.ERROR,
        "Supabase JWKS retrieval failed: details=%s attempt=%s retry=%s "
        "trust_env=True proxy_environment=%s\n%s",
        details,
        attempt + 1,
        will_retry,
        proxy_environment,
        _safe_traceback(exc),
    )


def _resolve_supabase_addresses(hostname: str, timeout: float = 0.3) -> tuple[dict[str, Any], list[tuple]]:
    result_queue: queue.Queue = queue.Queue(maxsize=1)

    def resolve() -> None:
        try:
            result_queue.put((socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM), None))
        except Exception as exc:
            result_queue.put((None, exc))

    # getaddrinfo has no timeout argument, so isolate it from the request thread.
    threading.Thread(target=resolve, name="supabase-jwks-dns-probe", daemon=True).start()
    try:
        records, error = result_queue.get(timeout=timeout)
    except queue.Empty:
        return {"status": "timeout", "addresses": []}, []
    if error is not None:
        return {"status": "failed", "failure": _jwks_failure_details(error), "addresses": []}, []

    addresses = []
    candidates = []
    seen = set()
    for family, socktype, proto, _, sockaddr in records:
        ip_address = sockaddr[0]
        identity = (family, socktype, proto, ip_address)
        if identity in seen:
            continue
        seen.add(identity)
        addresses.append({
            "family": socket.AddressFamily(family).name,
            "socket_type": socket.SocketKind(socktype).name,
            "ip": ip_address,
        })
        candidates.append((family, socktype, proto, sockaddr))
        if len(candidates) == 8:
            break
    return {
        "status": "ok",
        "addresses": addresses,
        "truncated": len(records) > len(candidates),
    }, candidates


def _probe_direct_socket(
    family: int,
    socktype: int,
    proto: int,
    sockaddr: tuple,
    hostname: str,
    use_tls: bool,
) -> dict[str, Any]:
    raw_socket = None
    try:
        raw_socket = socket.socket(family, socktype, proto)
        raw_socket.settimeout(0.2)
        raw_socket.connect(sockaddr)
        if use_tls:
            tls_socket = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=hostname)
            raw_socket = None
            with tls_socket:
                tls_socket.settimeout(0.2)
                tls_socket.do_handshake()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "failed", "failure": _jwks_failure_details(exc)}
    finally:
        if raw_socket is not None:
            raw_socket.close()


def _probe_supabase_network(jwks_url: str) -> dict[str, Any]:
    hostname = urlsplit(jwks_url).hostname
    if not hostname:
        return {"status": "invalid_supabase_hostname"}

    dns_result, addresses = _resolve_supabase_addresses(hostname)
    result: dict[str, Any] = {
        "hostname": hostname,
        "dns": dns_result,
        "direct_tcp": [],
        "direct_tls": [],
        "httpx": None,
    }
    for family, socktype, proto, sockaddr in addresses[:2]:
        target = sockaddr[0]
        tcp_result = _probe_direct_socket(family, socktype, proto, sockaddr, hostname, False)
        result["direct_tcp"].append({"ip": target, **tcp_result})
        if tcp_result["status"] == "ok":
            tls_result = _probe_direct_socket(family, socktype, proto, sockaddr, hostname, True)
            result["direct_tls"].append({"ip": target, **tls_result})

    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=0.35, read=0.35, write=0.2, pool=0.15),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            trust_env=True,
        ) as client:
            with client.stream("GET", jwks_url) as response:
                http_status = response.status_code
        result["httpx"] = {"status": "response", "http_status": http_status}
    except Exception as exc:
        result["httpx"] = {"status": "failed", "failure": _jwks_failure_details(exc)}
    result["proxy_environment"] = {
        "HTTP_PROXY": bool(os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")),
        "HTTPS_PROXY": bool(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")),
        "ALL_PROXY": bool(os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")),
        "NO_PROXY": bool(os.environ.get("NO_PROXY") or os.environ.get("no_proxy")),
    }
    return result


def _run_supabase_network_diagnostic(jwks_url: str) -> None:
    global _jwks_diagnostic_started

    with _jwks_diagnostic_lock:
        if _jwks_diagnostic_started:
            logger.warning("JWKS_DIAGNOSTIC_SKIP reason=already_run")
            return
        _jwks_diagnostic_started = True

    try:
        result = _probe_supabase_network(jwks_url)
        logger.warning("Temporary Supabase JWKS network diagnostic: %s", result)
    except Exception as exc:
        logger.warning(
            "Temporary Supabase JWKS network diagnostic failed: %s\n%s",
            _jwks_failure_details(exc),
            _safe_traceback(exc),
        )


def _run_jwks_diagnostic_safely(jwks_url: str) -> None:
    logger.warning("JWKS_DIAGNOSTIC_START")
    try:
        _run_supabase_network_diagnostic(jwks_url)
    except Exception as exc:
        logger.warning(
            "JWKS_DIAGNOSTIC_ERROR: %s\n%s",
            _jwks_failure_details(exc),
            _safe_traceback(exc),
        )
    finally:
        logger.warning("JWKS_DIAGNOSTIC_COMPLETE")


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
                try:
                    _discard_jwks_client()
                except Exception as cleanup_exc:
                    logger.warning(
                        "JWKS_CLIENT_CLEANUP_ERROR: %s\n%s",
                        _jwks_failure_details(cleanup_exc),
                        _safe_traceback(cleanup_exc),
                    )
                logger.warning("JWKS_ASYNC_RESOLVER_FALLBACK_START")
                try:
                    keys = _fetch_supabase_jwks_with_async_resolver(jwks_url)
                except Exception as fallback_exc:
                    logger.warning(
                        "JWKS_ASYNC_RESOLVER_FALLBACK_COMPLETE status=failed details=%s\n%s",
                        _jwks_failure_details(fallback_exc),
                        _safe_traceback(fallback_exc),
                    )
                else:
                    _jwks_cache.update({
                        "url": jwks_url,
                        "keys": keys,
                        "expires_at": time.monotonic() + 480,
                    })
                    logger.warning("JWKS_ASYNC_RESOLVER_FALLBACK_COMPLETE status=success")
                    return keys
                _run_jwks_diagnostic_safely(jwks_url)
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
