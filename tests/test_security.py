"""Secret redaction + SSRF guard tests (PRODUCT_PLAN.md §6.4, §9.3)."""

from __future__ import annotations

from app.security.outbound_url import OutboundUrlValidator, _is_forbidden, pin_connect_target
from app.security.secrets import RedactedSecret, ephemeral_secret


def test_redacted_secret_never_leaks_raw():
    secret = RedactedSecret("sk-123-secret")
    assert "sk-123-secret" not in repr(secret)
    assert "sk-123-secret" not in str(secret)
    assert secret.expose() == "sk-123-secret"


def test_ephemeral_secret_clears_reference_after_context():
    async def scenario():
        secret_holder = {}
        async with ephemeral_secret("sk-abc") as s:
            secret_holder["s"] = s
            assert s.expose() == "sk-abc"
        # After the context, the holder's raw reference is dropped.
        assert secret_holder["s"].expose() is None

    import asyncio
    asyncio.run(scenario())


def test_ssrf_rejects_private_and_loopback(monkeypatch):
    # Stub resolution so the test is deterministic and offline.
    def fake_getaddrinfo(host, port):
        if host == "localhost":
            return [(2, 1, 6, "", ("127.0.0.1", 0))]
        if host == "internal.corp":
            return [(2, 1, 6, "", ("10.0.0.5", 0))]
        if host == "metadata.internal":
            return [(2, 1, 6, "", ("169.254.169.254", 0))]
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    import app.security.outbound_url as mod
    monkeypatch.setattr(mod.socket, "getaddrinfo", fake_getaddrinfo)

    validator = OutboundUrlValidator([])
    assert not validator.validate("https://localhost/x").allowed
    assert not validator.validate("https://internal.corp/x").allowed
    assert not validator.validate("https://metadata.internal/x").allowed


def test_ssrf_allows_public_https(monkeypatch):
    def fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    import app.security.outbound_url as mod
    monkeypatch.setattr(mod.socket, "getaddrinfo", fake_getaddrinfo)

    validator = OutboundUrlValidator([])
    policy = validator.validate("https://api.example.com/v1")
    assert policy.allowed


def test_ssrf_rejects_non_https():
    validator = OutboundUrlValidator([])
    assert not validator.validate("http://api.example.com/v1").allowed


def test_ssrf_allowlist_short_circuits_dns():
    validator = OutboundUrlValidator(["api.example.com"])
    # Allowlisted host is allowed without DNS resolution.
    assert validator.validate("https://api.example.com/v1").allowed


def test_is_forbidden_metadata():
    import ipaddress
    assert _is_forbidden(ipaddress.ip_address("169.254.169.254"))
    assert _is_forbidden(ipaddress.ip_address("127.0.0.1"))
    assert _is_forbidden(ipaddress.ip_address("10.1.2.3"))
    assert not _is_forbidden(ipaddress.ip_address("93.184.216.34"))


def test_validate_returns_the_resolved_ip_for_pinning(monkeypatch):
    """Callers must pin the connection to this IP (DNS-rebinding guard)."""
    def fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    import app.security.outbound_url as mod
    monkeypatch.setattr(mod.socket, "getaddrinfo", fake_getaddrinfo)

    policy = OutboundUrlValidator([]).validate("https://api.example.com/v1")
    assert policy.allowed
    assert policy.resolved_ip == "93.184.216.34"


def test_allowlisted_host_has_no_resolved_ip():
    # No DNS lookup performed for allowlisted hosts, so nothing to pin to —
    # callers must fall back to connecting by hostname for these.
    policy = OutboundUrlValidator(["api.example.com"]).validate("https://api.example.com/v1")
    assert policy.allowed
    assert policy.resolved_ip is None


def test_pin_connect_target_rewrites_host_to_ip_and_keeps_path():
    pinned, original_host = pin_connect_target(
        "https://api.example.com/v1/chat/completions", "93.184.216.34",
    )
    assert pinned == "https://93.184.216.34/v1/chat/completions"
    assert original_host == "api.example.com"


def test_pin_connect_target_preserves_explicit_port():
    pinned, original_host = pin_connect_target("https://api.example.com:8443/x", "93.184.216.34")
    assert pinned == "https://93.184.216.34:8443/x"
    assert original_host == "api.example.com"


def test_pin_connect_target_brackets_ipv6():
    pinned, original_host = pin_connect_target("https://api.example.com/x", "2001:db8::1")
    assert pinned == "https://[2001:db8::1]/x"
    assert original_host == "api.example.com"


def test_dns_rebind_between_validate_and_connect_is_neutralised(monkeypatch):
    """The classic TOCTOU: validate() sees a public IP, but a second DNS lookup
    (what the naive pre-fix code relied on implicitly) would return a private
    one. Pinning to the already-validated IP means that second lookup is never
    made, so the rebind has no effect on where the request actually goes."""
    calls = {"n": 0}

    def rebinding_getaddrinfo(host, port):
        calls["n"] += 1
        # First call (validation) sees a safe public address...
        if calls["n"] == 1:
            return [(2, 1, 6, "", ("93.184.216.34", 0))]
        # ...a later call (if anything re-resolved) would see a rebound
        # internal address. A correct caller must never trigger this second
        # call for the connection itself.
        return [(2, 1, 6, "", ("127.0.0.1", 0))]

    import app.security.outbound_url as mod
    monkeypatch.setattr(mod.socket, "getaddrinfo", rebinding_getaddrinfo)

    policy = OutboundUrlValidator([]).validate("https://rebind.example.com/v1")
    assert policy.allowed
    assert policy.resolved_ip == "93.184.216.34"

    pinned_url, _ = pin_connect_target("https://rebind.example.com/v1/chat/completions", policy.resolved_ip)
    # The connection target embeds the validated IP directly — no hostname
    # left for a transport-level resolver to look up (and rebind) again.
    assert "rebind.example.com" not in pinned_url
    assert pinned_url.startswith("https://93.184.216.34")