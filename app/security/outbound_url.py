"""SSRF guard for custom AI base URLs (PRODUCT_PLAN.md §9.3).

A user-supplied base URL on a self-hosted instance is a SSRF vector. This
module resolves the host and rejects loopback, link-local, private, and cloud
metadata addresses before any request is made. The allowlist shortcut
(``APP_AI_ALLOWED_BASE_URLS``) is provided for administrators who explicitly
trust specific endpoints.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

# IPv4-mapped IPv6 prefixes (e.g. ::ffff:127.0.0.1) — resolve to their embedded
# IPv4 address so the private/loopback check still catches them.
_IPV4_MAPPED = ipaddress.ip_network("::ffff:0:0/96")


@dataclass(frozen=True)
class UrlPolicy:
    """Resolved verdict for one outbound URL.

    ``resolved_ip`` is the address that was actually checked. Callers MUST
    connect to this IP (pinning it, e.g. via httpx's ``sni_hostname``
    extension) rather than letting the HTTP client re-resolve the hostname —
    otherwise a validated-then-rebound DNS record lets the guard be bypassed
    entirely between validation and connection (TOCTOU). ``None`` when the
    host was allowlisted (no resolution performed) or validation failed.
    """

    url: str
    host: str
    allowed: bool
    reason: str | None = None
    resolved_ip: str | None = None


class OutboundUrlValidator:
    """Validates that a base URL is safe to call from the server."""

    def __init__(self, allowlist: list[str] | None = None) -> None:
        self._allowlist = _normalise_allowlist(allowlist or [])

    def validate(self, raw_url: str) -> UrlPolicy:
        parsed = urlparse(raw_url)

        if parsed.scheme != "https":
            return UrlPolicy(raw_url, parsed.hostname or raw_url, False,
                             "only https base URLs are allowed")

        host = parsed.hostname
        if not host:
            return UrlPolicy(raw_url, raw_url, False, "base URL has no host")

        if _host_in_allowlist(host, self._allowlist):
            return UrlPolicy(raw_url, host, True)

        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            return UrlPolicy(raw_url, host, False, f"cannot resolve host: {exc}")

        addresses = {_extract_ip(info[4][0]) for info in infos}
        safe_addr = None
        for addr in addresses:
            ip = ipaddress.ip_address(addr)
            if _is_forbidden(ip):
                return UrlPolicy(raw_url, host, False,
                                 f"host resolves to forbidden address {addr}")
            safe_addr = safe_addr or addr

        return UrlPolicy(raw_url, host, True, resolved_ip=safe_addr)

    def validate_redirect(self, raw_url: str) -> UrlPolicy:
        """Validate a redirect target with the same rules as the origin."""
        return self.validate(raw_url)


def pin_connect_target(raw_url: str, resolved_ip: str) -> tuple[str, str]:
    """Rewrite ``raw_url`` so the connection targets ``resolved_ip`` directly.

    Returns ``(pinned_url, original_host)``. The caller must still send the
    original host as the ``Host`` header and as the TLS SNI name (httpx's
    ``sni_hostname`` request extension) so certificate validation keeps
    checking the real hostname — only the DNS-resolution step is pinned.
    """
    parsed = urlparse(raw_url)
    host = parsed.hostname
    netloc = f"[{resolved_ip}]" if ":" in resolved_ip else resolved_ip
    if parsed.port:
        netloc += f":{parsed.port}"
    pinned = parsed._replace(netloc=netloc).geturl()
    return pinned, host


def _normalise_allowlist(entries: list[str]) -> set[str]:
    out = set()
    for entry in entries:
        parsed = urlparse(entry if "://" in entry else f"https://{entry}")
        host = parsed.hostname
        if host:
            out.add(host.lower())
    return out


def _host_in_allowlist(host: str, allowlist: set[str]) -> bool:
    host = host.lower()
    if host in allowlist:
        return True
    # Allow a bare host entry to cover its subdomains too.
    return any(host == entry or host.endswith("." + entry) for entry in allowlist)


def _extract_ip(addr: str) -> str:
    """Unwrap IPv4-mapped IPv6 addresses so the real address is checked."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return addr
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return str(ip.ipv4_mapped)
    return addr


def _is_forbidden(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_multicast
        or ip.is_reserved
        or _is_cloud_metadata(ip)
    )


def _is_cloud_metadata(ip: ipaddress._BaseAddress) -> bool:
    """Cloud instance metadata endpoints (AWS/GCP/Azure) — block by IP."""
    metadata = (
        ipaddress.ip_address("169.254.169.254"),   # AWS / GCP / Azure
        ipaddress.ip_address("100.100.100.200"),   # Alibaba Cloud
    )
    return ip in metadata