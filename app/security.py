from __future__ import annotations

import hashlib
import hmac
import ipaddress

from fastapi import Request

from app.settings import Settings


def _trusted_peer(peer: str, cidrs: list[str]) -> bool:
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(address in ipaddress.ip_network(cidr) for cidr in cidrs)


def get_client_ip(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    if _trusted_peer(peer, settings.trusted_proxy_cidrs):
        # The isolated Caddy proxy overwrites X-Real-IP; the API port is loopback-only.
        forwarded = request.headers.get("x-real-ip", "").strip()
        try:
            return str(ipaddress.ip_address(forwarded)) if forwarded else peer
        except ValueError:
            return peer
    return peer


def get_client_country(request: Request, settings: Settings) -> str | None:
    """Cloudflare's visitor country, trusted only when the request came through the proxy."""
    peer = request.client.host if request.client else "unknown"
    if not _trusted_peer(peer, settings.trusted_proxy_cidrs):
        return None
    country = request.headers.get("cf-ipcountry", "").strip().upper()
    return country if len(country) == 2 and country.isalnum() else None


def hash_ip(ip: str, salt: str) -> str:
    return hmac.new(salt.encode(), ip.encode(), hashlib.sha256).hexdigest()


def valid_verification_token(provided: str | None, expected: str) -> bool:
    return bool(provided) and hmac.compare_digest(provided, expected)
