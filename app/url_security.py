import asyncio
import socket
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import cast
from urllib.parse import urlsplit


class UnsafeUrlError(ValueError):
    """Raised when a URL target is not safe for outbound probing."""


def validate_public_http_url(url: str) -> None:
    """Validate URL syntax that can be checked without DNS."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("service URL must use http or https")
    if not parsed.hostname:
        raise UnsafeUrlError("service URL must include a hostname")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("service URL must not include credentials")
    _validate_hostname_literal(parsed.hostname)


async def ensure_public_http_target(url: str) -> None:
    """Resolve a URL hostname and reject non-public network targets."""
    validate_public_http_url(url)
    parsed = urlsplit(url)
    host = parsed.hostname
    if host is None:
        raise UnsafeUrlError("service URL must include a hostname")

    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    resolved_addresses = await asyncio.to_thread(_resolve_addresses, host, port)
    if not resolved_addresses:
        raise UnsafeUrlError("service hostname did not resolve")
    for address in resolved_addresses:
        _validate_ip_address(address)


def _validate_hostname_literal(hostname: str) -> None:
    """Reject unsafe hostname literals and IP literals before DNS lookup."""
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        raise UnsafeUrlError("service hostname must not target localhost")
    try:
        address = ip_address(normalized)
    except ValueError:
        return
    _validate_ip_address(address)


def _validate_ip_address(address_text: str | IPv4Address | IPv6Address) -> None:
    """Allow only globally routable IP addresses."""
    address = ip_address(address_text)
    if not address.is_global:
        raise UnsafeUrlError("service URL must resolve to a public IP address")


def _resolve_addresses(host: str, port: int) -> set[str]:
    """Resolve host addresses using the system resolver."""
    try:
        results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError("service hostname did not resolve") from exc
    return {cast(str, result[4][0]) for result in results}
