import asyncio
import logging
import os
import socket
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import aiohttp
import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException
from jose import jwt, jwk

from backend.app.core import security
from backend.app.core.config import settings


PROJECT_URL = "https://formease-test.supabase.co"
TEST_SECRET = "test-jwks-secret-sentinel"


@pytest.fixture(autouse=True)
def isolate_jwks_state(monkeypatch):
    if security._jwks_client is not None:
        security._jwks_client.close()
    monkeypatch.setattr(security, "_jwks_client", None)
    monkeypatch.setattr(
        security,
        "_jwks_cache",
        {"keys": [], "expires_at": 0.0, "url": ""},
    )
    monkeypatch.setattr(settings, "SUPABASE_URL", PROJECT_URL)
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_SECRET)
    yield
    if security._jwks_client is not None:
        security._jwks_client.close()


class FakeClient:
    def __init__(self, *outcomes: Any):
        self.outcomes = list(outcomes)
        self.calls = []
        self.closed = False
        self.lock = threading.Lock()

    def get(self, url: str):
        with self.lock:
            self.calls.append(url)
            outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close(self):
        self.closed = True


def response_with_keys(keys: list[dict[str, Any]]) -> httpx.Response:
    request = httpx.Request("GET", f"{PROJECT_URL}/auth/v1/.well-known/jwks.json")
    return httpx.Response(200, json={"keys": keys}, request=request)


def make_asymmetric_token(algorithm: str, kid: str = "test-signing-key", email: str = "user@example.com"):
    if algorithm == "ES256":
        private_key = ec.generate_private_key(ec.SECP256R1())
    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_jwk = jwk.construct(public_pem, algorithm=algorithm).to_dict()
    public_jwk.update({"kid": kid, "alg": algorithm})
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "email": email,
            "aud": "authenticated",
            "role": "authenticated",
            "iss": f"{PROJECT_URL}/auth/v1",
            "iat": now,
            "exp": now + 3600,
        },
        private_pem,
        algorithm=algorithm,
        headers={"kid": kid},
    )
    return token, public_jwk


def install_clients(monkeypatch, *clients: FakeClient):
    remaining = iter(clients)
    monkeypatch.setattr(security, "_create_jwks_client", lambda: next(remaining))


@pytest.mark.parametrize("algorithm", ["ES256", "RS256"])
def test_asymmetric_jwts_are_verified_with_supabase_jwks(monkeypatch, algorithm):
    token, public_jwk = make_asymmetric_token(algorithm)
    client = FakeClient(response_with_keys([public_jwk]))
    install_clients(monkeypatch, client)

    payload = security.verify_supabase_jwt(token)

    assert payload["aud"] == "authenticated"
    assert payload["iss"] == f"{PROJECT_URL}/auth/v1"
    assert payload["role"] == "authenticated"
    assert client.calls == [f"{PROJECT_URL}/auth/v1/.well-known/jwks.json"]


def test_jwks_cache_reuses_successful_response(monkeypatch):
    client = FakeClient(response_with_keys([{"kid": "cached"}]))
    install_clients(monkeypatch, client)

    first = security._get_supabase_jwks()
    second = security._get_supabase_jwks()

    assert first == second == [{"kid": "cached"}]
    assert len(client.calls) == 1


def test_missing_key_id_forces_jwks_refresh(monkeypatch):
    token, new_public_jwk = make_asymmetric_token("ES256", kid="rotated-key")
    old_public_jwk = {**new_public_jwk, "kid": "previous-key"}
    client = FakeClient(
        response_with_keys([old_public_jwk]),
        response_with_keys([new_public_jwk]),
    )
    install_clients(monkeypatch, client)

    payload = security.verify_supabase_jwt(token)

    assert payload["sub"]
    assert len(client.calls) == 2


def test_unknown_key_id_after_refresh_is_rejected(monkeypatch):
    token, public_jwk = make_asymmetric_token("ES256", kid="unknown-key")
    client = FakeClient(
        response_with_keys([{**public_jwk, "kid": "previous-key"}]),
        response_with_keys([{**public_jwk, "kid": "still-not-the-key"}]),
    )
    install_clients(monkeypatch, client)

    with pytest.raises(HTTPException) as error:
        security.verify_supabase_jwt(token)

    assert error.value.status_code == 401
    assert error.value.detail == "Invalid authentication token."
    assert len(client.calls) == 2


def test_transient_transport_failure_retries_without_caching_failure(monkeypatch):
    _, public_jwk = make_asymmetric_token("ES256")
    failed_client = FakeClient(httpx.ConnectError("temporary network failure"))
    recovered_client = FakeClient(response_with_keys([public_jwk]))
    delays = []
    monkeypatch.setattr(security.time, "sleep", delays.append)
    install_clients(monkeypatch, failed_client, recovered_client)

    keys = security._get_supabase_jwks()
    cached_keys = security._get_supabase_jwks()

    assert keys == cached_keys == [public_jwk]
    assert failed_client.closed
    assert len(failed_client.calls) == len(recovered_client.calls) == 1
    assert len(delays) == 1
    assert 0.05 <= delays[0] <= 0.15


def test_async_resolver_fallback_verifies_and_caches_jwks(monkeypatch, caplog):
    token, public_jwk = make_asymmetric_token("ES256")
    failed_clients = [
        FakeClient(httpx.ConnectError("sync DNS path unavailable")),
        FakeClient(httpx.ConnectError("sync DNS path unavailable")),
    ]
    fallback_calls = []
    install_clients(monkeypatch, *failed_clients)
    monkeypatch.setattr(
        security,
        "_fetch_supabase_jwks_with_async_resolver",
        lambda url: fallback_calls.append(url) or [public_jwk],
    )
    monkeypatch.setattr(
        security,
        "_run_jwks_diagnostic_safely",
        lambda _: pytest.fail("diagnostic should not run after fallback succeeds"),
    )
    caplog.set_level(logging.WARNING, logger=security.__name__)

    payload = security.verify_supabase_jwt(token)
    cached_keys = security._get_supabase_jwks()

    assert payload["aud"] == "authenticated"
    assert payload["iss"] == f"{PROJECT_URL}/auth/v1"
    assert fallback_calls == [f"{PROJECT_URL}/auth/v1/.well-known/jwks.json"]
    assert cached_keys == [public_jwk]
    assert [len(client.calls) for client in failed_clients] == [1, 1]
    assert "JWKS_ASYNC_RESOLVER_FALLBACK_START" in caplog.text
    assert "JWKS_ASYNC_RESOLVER_FALLBACK_COMPLETE status=success" in caplog.text


def test_async_resolver_uses_aiohttp_cares_connector_and_bounded_retry(monkeypatch):
    _, public_jwk = make_asymmetric_token("RS256")
    outcomes = [aiohttp.ClientConnectionError("private DNS error"), {"keys": [public_jwk]}]
    session_instances = []
    connector_options = []
    resolver_instances = []
    resolver_options = []

    class FakeResolver:
        def __init__(self, **kwargs):
            resolver_options.append(kwargs)
            resolver_instances.append(self)

    class FakeConnector:
        def __init__(self, **kwargs):
            connector_options.append(kwargs)

    class FakeResponse:
        status = 200

        def raise_for_status(self):
            return None

        async def json(self):
            return outcomes.pop(0)

    class FakeRequest:
        async def __aenter__(self):
            outcome = outcomes[0]
            if isinstance(outcome, Exception):
                outcomes.pop(0)
                raise outcome
            return FakeResponse()

        async def __aexit__(self, _exc_type, _exc_value, _traceback):
            return None

    class FakeSession:
        def __init__(self, **kwargs):
            self.options = kwargs
            self.calls = []
            session_instances.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc_value, _traceback):
            return None

        def get(self, url, **kwargs):
            self.calls.append(url)
            assert kwargs == {"allow_redirects": False}
            return FakeRequest()

    monkeypatch.setattr(security.aiohttp, "AsyncResolver", FakeResolver)
    monkeypatch.setattr(security.aiohttp, "TCPConnector", FakeConnector)
    monkeypatch.setattr(security.aiohttp, "ClientSession", FakeSession)

    keys = security._fetch_supabase_jwks_with_async_resolver(
        f"{PROJECT_URL}/auth/v1/.well-known/jwks.json",
    )

    assert keys == [public_jwk]
    assert len(session_instances) == 1
    assert len(session_instances[0].calls) == 2
    assert session_instances[0].options["trust_env"] is True
    assert connector_options[0]["resolver"] is resolver_instances[0]
    assert connector_options[0]["limit"] == 1
    assert connector_options[0]["ttl_dns_cache"] == 300
    assert resolver_options == [{"timeout": 1.0, "tries": 2}]


def test_async_resolver_fallback_has_an_overall_timeout(monkeypatch):
    async def hang_forever(_url):
        await asyncio.Event().wait()

    monkeypatch.setattr(security, "_JWKS_ASYNC_FETCH_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(security, "_fetch_supabase_jwks_async", hang_forever)
    started = time.monotonic()

    with pytest.raises(asyncio.TimeoutError):
        security._fetch_supabase_jwks_with_async_resolver(
            f"{PROJECT_URL}/auth/v1/.well-known/jwks.json",
        )

    assert time.monotonic() - started < 0.5


def test_concurrent_cache_misses_share_one_jwks_request(monkeypatch):
    barrier = threading.Barrier(8)
    _, public_jwk = make_asymmetric_token("ES256")
    client = FakeClient(response_with_keys([public_jwk]))
    install_clients(monkeypatch, client)

    def retrieve_keys():
        barrier.wait()
        return security._get_supabase_jwks()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: retrieve_keys(), range(8)))

    assert results == [[public_jwk]] * 8
    assert len(client.calls) == 1


def test_jwks_failure_logs_traceback_but_not_token_or_secrets(monkeypatch, caplog):
    email = "private-user-email-sentinel"
    token, _ = make_asymmetric_token("ES256", email=email)
    proxy_url = "https://proxy-user:proxy-password@proxy.invalid"
    monkeypatch.setenv("HTTPS_PROXY", proxy_url)

    def connect_busy():
        error = httpx.ConnectError("device is busy")
        error.__cause__ = OSError(16, os.strerror(16))
        return error

    failed_clients = [
        FakeClient(connect_busy()),
        FakeClient(connect_busy()),
        FakeClient(connect_busy()),
        FakeClient(connect_busy()),
    ]
    install_clients(monkeypatch, *failed_clients)
    monkeypatch.setattr(security, "_run_supabase_network_diagnostic", lambda _: None)
    monkeypatch.setattr(
        security,
        "_fetch_supabase_jwks_with_async_resolver",
        lambda _: (_ for _ in ()).throw(httpx.ConnectError("private fallback error")),
    )
    caplog.set_level(logging.WARNING, logger=security.__name__)

    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            security.verify_supabase_jwt(token)
        assert error.value.status_code == 503
        assert "device is busy" not in error.value.detail

    assert "Traceback" in caplog.text
    assert "'phase': 'tcp_connect'" in caplog.text
    assert "'os_errno': 16" in caplog.text
    assert "'strerror': '<redacted>'" not in caplog.text
    assert "'HTTPS_PROXY': True" in caplog.text
    assert "device is busy" not in caplog.text
    assert token not in caplog.text
    assert email not in caplog.text
    assert TEST_SECRET not in caplog.text
    assert proxy_url not in caplog.text
    assert security._jwks_cache == {"keys": [], "expires_at": 0.0, "url": ""}
    assert [len(client.calls) for client in failed_clients] == [1, 1, 1, 1]


def test_terminal_failure_marks_probe_and_preserves_original_auth_error(monkeypatch, caplog):
    token, _ = make_asymmetric_token("ES256")
    clients = [
        FakeClient(httpx.ConnectError("original network error")),
        FakeClient(httpx.ConnectError("original network error")),
    ]
    install_clients(monkeypatch, *clients)
    discard_count = 0
    diagnostic_calls = []

    def discard_client():
        nonlocal discard_count
        discard_count += 1
        security._jwks_client = None
        if discard_count == 2:
            raise OSError(16, "private cleanup message")

    def fail_diagnostic(url):
        diagnostic_calls.append(url)
        raise RuntimeError("private diagnostic message")

    monkeypatch.setattr(security, "_discard_jwks_client", discard_client)
    monkeypatch.setattr(
        security,
        "_fetch_supabase_jwks_with_async_resolver",
        lambda _: (_ for _ in ()).throw(RuntimeError("private fallback message")),
    )
    monkeypatch.setattr(security, "_run_supabase_network_diagnostic", fail_diagnostic)
    caplog.set_level(logging.WARNING, logger=security.__name__)

    with pytest.raises(HTTPException) as error:
        security.verify_supabase_jwt(token)

    assert error.value.status_code == 503
    assert error.value.detail == "Unable to retrieve Supabase signing keys."
    assert diagnostic_calls == [f"{PROJECT_URL}/auth/v1/.well-known/jwks.json"]
    assert caplog.text.index("JWKS_DIAGNOSTIC_START") < caplog.text.index("JWKS_DIAGNOSTIC_ERROR")
    assert caplog.text.index("JWKS_DIAGNOSTIC_ERROR") < caplog.text.index("JWKS_DIAGNOSTIC_COMPLETE")
    assert "private cleanup message" not in caplog.text
    assert "private fallback message" not in caplog.text
    assert "private diagnostic message" not in caplog.text
    assert "original network error" not in caplog.text


def test_exception_chain_follows_cause_and_context_with_cycle_protection():
    outer = RuntimeError("private outer message")
    cause = OSError(16, os.strerror(16))
    context = socket.gaierror(-2, "private DNS message")
    outer.__cause__ = cause
    outer.__context__ = context
    context.__cause__ = outer

    chain = security._exception_chain(outer)
    details = security._os_error_details(outer)

    assert {type(error) for error in chain} == {RuntimeError, OSError, socket.gaierror}
    assert len(chain) == 3
    assert any(
        error["exception_class"] == "OSError"
        and error["errno"] == 16
        and error["strerror"] == os.strerror(16)
        for error in details
    )
    assert "private outer message" not in repr(details)
    assert "private DNS message" not in repr(details)


def test_dns_resolution_failure_reports_safe_cause_details(monkeypatch):
    monkeypatch.setattr(
        security.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(socket.gaierror(-2, "private DNS message")),
    )

    result, addresses = security._resolve_supabase_addresses("formease-test.supabase.co")

    assert result["status"] == "failed"
    assert result["failure"]["phase"] == "dns"
    assert result["failure"]["os_errors"][0]["exception_class"] == "gaierror"
    assert addresses == []
    assert "private DNS message" not in repr(result)


def test_dns_resolution_timeout_does_not_block_caller(monkeypatch):
    release_resolver = threading.Event()

    def blocked_getaddrinfo(*_args, **_kwargs):
        release_resolver.wait(1)
        return []

    monkeypatch.setattr(security.socket, "getaddrinfo", blocked_getaddrinfo)
    started = time.monotonic()
    try:
        result, addresses = security._resolve_supabase_addresses(
            "formease-test.supabase.co",
            timeout=0.02,
        )
    finally:
        release_resolver.set()

    assert time.monotonic() - started < 0.2
    assert result == {"status": "timeout", "addresses": []}
    assert addresses == []


def test_dns_resolution_records_family_socket_type_and_ip(monkeypatch):
    record = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "unused", ("203.0.113.20", 443))
    monkeypatch.setattr(security.socket, "getaddrinfo", lambda *_args, **_kwargs: [record])

    result, candidates = security._resolve_supabase_addresses("formease-test.supabase.co")

    assert result == {
        "status": "ok",
        "addresses": [{
            "family": "AF_INET",
            "socket_type": "SOCK_STREAM",
            "ip": "203.0.113.20",
        }],
        "truncated": False,
    }
    assert candidates == [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, ("203.0.113.20", 443))]


def test_direct_tcp_probe_reports_errno_without_raw_error_text(monkeypatch):
    class FailingSocket:
        def settimeout(self, _timeout):
            pass

        def connect(self, _address):
            raise OSError(16, "private socket error message")

        def close(self):
            pass

    monkeypatch.setattr(security.socket, "socket", lambda *_args: FailingSocket())

    result = security._probe_direct_socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
        0,
        ("192.0.2.1", 443),
        "formease-test.supabase.co",
        False,
    )

    assert result["status"] == "failed"
    assert result["failure"]["phase"] == "tcp_connect"
    assert result["failure"]["os_errors"][0]["errno"] == 16
    assert result["failure"]["os_errors"][0]["strerror"] == "<redacted>"
    assert "private socket error message" not in repr(result)


def test_network_probe_records_dns_tcp_tls_and_httpx_results(monkeypatch):
    hostname = "formease-test.supabase.co"
    url = f"https://{hostname}/auth/v1/.well-known/jwks.json"
    proxy_url = "https://proxy-user:proxy-password@proxy.invalid"
    monkeypatch.setenv("HTTPS_PROXY", proxy_url)
    candidate = (socket.AF_INET, socket.SOCK_STREAM, 6, ("203.0.113.10", 443))
    dns_result = {
        "status": "ok",
        "addresses": [{
            "family": "AF_INET",
            "socket_type": "SOCK_STREAM",
            "ip": "203.0.113.10",
        }],
        "truncated": False,
    }

    client_options = []

    class FakeHttpxClient:
        def __init__(self, **kwargs):
            self.options = kwargs
            client_options.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc_value, _exc_traceback):
            pass

        @contextmanager
        def stream(self, method, request_url):
            assert method == "GET"
            assert request_url == url
            yield SimpleNamespace(status_code=200)

    monkeypatch.setattr(
        security,
        "_resolve_supabase_addresses",
        lambda _: (dns_result, [candidate]),
    )
    monkeypatch.setattr(security, "_probe_direct_socket", lambda *_args: {"status": "ok"})
    monkeypatch.setattr(security.httpx, "Client", FakeHttpxClient)

    result = security._probe_supabase_network(url)

    assert result["dns"] == dns_result
    assert result["direct_tcp"] == [{"ip": "203.0.113.10", "status": "ok"}]
    assert result["direct_tls"] == [{"ip": "203.0.113.10", "status": "ok"}]
    assert result["httpx"] == {"status": "response", "http_status": 200}
    assert result["proxy_environment"]["HTTPS_PROXY"]
    assert client_options[0]["trust_env"] is True
    assert "headers" not in client_options[0]
    assert proxy_url not in repr(result)


def test_temporary_network_diagnostic_runs_only_once(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(security, "_jwks_diagnostic_started", False)
    monkeypatch.setattr(
        security,
        "_probe_supabase_network",
        lambda url: calls.append(url) or {"httpx": {"status": "response", "http_status": 200}},
    )
    caplog.set_level(logging.WARNING, logger=security.__name__)

    url = f"{PROJECT_URL}/auth/v1/.well-known/jwks.json"
    security._run_supabase_network_diagnostic(url)
    security._run_supabase_network_diagnostic(url)

    assert calls == [url]
    assert caplog.text.count("Temporary Supabase JWKS network diagnostic:") == 1
    assert "JWKS_DIAGNOSTIC_SKIP reason=already_run" in caplog.text


def test_network_diagnostic_failure_is_logged_without_escaping(monkeypatch, caplog):
    monkeypatch.setattr(security, "_jwks_diagnostic_started", False)
    monkeypatch.setattr(
        security,
        "_probe_supabase_network",
        lambda _: (_ for _ in ()).throw(RuntimeError("private diagnostic detail")),
    )
    caplog.set_level(logging.WARNING, logger=security.__name__)

    security._run_supabase_network_diagnostic(
        f"{PROJECT_URL}/auth/v1/.well-known/jwks.json",
    )

    assert "Temporary Supabase JWKS network diagnostic failed:" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "private diagnostic detail" not in caplog.text


def test_jwks_failure_classifier_distinguishes_dns_proxy_timeout_and_http_status():
    dns_error = httpx.ConnectError("DNS lookup failed")
    dns_error.__cause__ = socket.gaierror(-2, "name resolution failed")
    connect_error = httpx.ConnectError("connect failed")
    connect_error.__cause__ = OSError(16, "Device or resource busy")
    http_response = httpx.Response(
        503,
        request=httpx.Request("GET", f"{PROJECT_URL}/auth/v1/.well-known/jwks.json"),
    )
    http_error = httpx.HTTPStatusError(
        "server error",
        request=http_response.request,
        response=http_response,
    )

    assert security._classify_jwks_failure(dns_error) == ("dns", None, None)
    assert security._classify_jwks_failure(connect_error) == ("tcp_connect", 16, None)
    assert security._classify_jwks_failure(httpx.ProxyError("proxy failed")) == ("proxy", None, None)
    assert security._classify_jwks_failure(httpx.ConnectTimeout("connect timed out")) == (
        "timeout_connecttimeout",
        None,
        None,
    )
    assert security._classify_jwks_failure(http_error) == ("http_response", None, 503)


@pytest.mark.parametrize("algorithm", ["ES256", "RS256"])
def test_asymmetric_invalid_signature_is_rejected(monkeypatch, algorithm):
    token, _ = make_asymmetric_token(algorithm)
    _, different_public_jwk = make_asymmetric_token(algorithm)
    different_public_jwk["kid"] = jwt.get_unverified_header(token)["kid"]
    client = FakeClient(response_with_keys([different_public_jwk]))
    install_clients(monkeypatch, client)

    with pytest.raises(HTTPException) as error:
        security.verify_supabase_jwt(token)

    assert error.value.status_code == 401
    assert error.value.detail == "Invalid authentication token."
